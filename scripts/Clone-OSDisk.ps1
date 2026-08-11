<#
.SYNOPSIS
    Clones a running Windows OS installation from one physical disk to another,
    producing a bootable copy of the operating system on the target disk.

.DESCRIPTION
    Performs a file-level clone of the OS disk that is safe to run from inside
    the running operating system:

      1. Auto-detects (or accepts) the source OS disk and validates the target.
      2. Wipes the target disk and recreates a standard UEFI/GPT layout
         (EFI System Partition, MSR, and an NTFS OS partition).
      3. Takes a Volume Shadow Copy (VSS) snapshot of the OS volume so open
         files (registry hives, databases, etc.) are copied in a consistent state.
      4. Mirrors the snapshot to the new OS partition with robocopy in backup
         mode, preserving ACLs, attributes, timestamps, and symbolic links.
      5. Rebuilds the boot environment on the target with bcdboot, so the new
         disk boots on its own (no stale BCD entries pointing at the old disk).

    Requirements / limitations:
      - Must be run from an elevated (Administrator) PowerShell session.
      - Source must be a GPT disk on a UEFI system (standard since Windows 8).
        MBR/BIOS systems are detected and rejected with an explanation.
      - The target disk is COMPLETELY ERASED. The script refuses to run against
        the disk Windows is currently booted from and requires explicit
        confirmation (or -Force) before wiping the target.
      - The target must be at least as large as the data used on the source.
      - A recovery (WinRE) partition is not recreated; Windows boots and runs
        without it, and it can be rebuilt later with 'reagentc /enable'.
      - If the source volume is BitLocker-encrypted, the clone is written
        DECRYPTED. Re-enable BitLocker on the target after first boot.

.PARAMETER TargetDiskNumber
    Disk number (as shown by Get-Disk) of the disk to clone TO.
    All data on this disk will be destroyed.

.PARAMETER SourceDiskNumber
    Disk number of the disk to clone FROM. Defaults to the disk that hosts the
    current system drive (usually C:).

.PARAMETER Force
    Skips the interactive "type ERASE <n> to continue" confirmation.
    Intended for automation; use with care.

.PARAMETER LogPath
    Path of the log file. Defaults to Clone-OSDisk_<timestamp>.log in %TEMP%.

.EXAMPLE
    PS> .\Clone-OSDisk.ps1 -TargetDiskNumber 1

    Clones the current OS disk onto disk 1 after interactive confirmation.

.EXAMPLE
    PS> .\Clone-OSDisk.ps1 -SourceDiskNumber 0 -TargetDiskNumber 2 -Force

    Non-interactive clone of disk 0 onto disk 2 (disk 2 is erased without prompting).

.NOTES
    After the clone completes: shut down, swap the disks (or pick the new disk
    from the firmware boot menu), and boot. Because bcdboot regenerates the
    boot files, the clone boots independently of the original disk.
#>

#Requires -Version 5.1
#Requires -RunAsAdministrator

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(0, 512)]
    [int]$TargetDiskNumber,

    [Parameter()]
    [ValidateRange(0, 512)]
    [int]$SourceDiskNumber = -1,

    [Parameter()]
    [switch]$Force,

    [Parameter()]
    [string]$LogPath = (Join-Path $env:TEMP ("Clone-OSDisk_{0:yyyyMMdd_HHmmss}.log" -f (Get-Date)))
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Write-Log {
    param(
        [Parameter(Mandatory)][string]$Message,
        [ValidateSet('INFO', 'WARN', 'ERROR', 'OK')][string]$Level = 'INFO'
    )
    $line = "[{0:yyyy-MM-dd HH:mm:ss}] [{1,-5}] {2}" -f (Get-Date), $Level, $Message
    Add-Content -Path $LogPath -Value $line
    switch ($Level) {
        'ERROR' { Write-Host $line -ForegroundColor Red }
        'WARN'  { Write-Host $line -ForegroundColor Yellow }
        'OK'    { Write-Host $line -ForegroundColor Green }
        default { Write-Host $line }
    }
}

function Get-FreeDriveLetter {
    param([string[]]$Exclude = @())
    $inUse = @((Get-PSDrive -PSProvider FileSystem).Name) + $Exclude
    $letter = [char[]]('Z'[0]..'D'[0]) | Where-Object { "$_" -notin $inUse } | Select-Object -First 1
    if (-not $letter) { throw "No free drive letters available." }
    return [string]$letter
}

function Format-Size {
    param([uint64]$Bytes)
    if ($Bytes -ge 1TB) { return "{0:N2} TB" -f ($Bytes / 1TB) }
    if ($Bytes -ge 1GB) { return "{0:N2} GB" -f ($Bytes / 1GB) }
    return "{0:N0} MB" -f ($Bytes / 1MB)
}

# State used by the cleanup block
$script:ShadowCopy    = $null
$script:ShadowLink    = $null
$script:TempLetters   = @()

function Invoke-Cleanup {
    if ($script:ShadowLink -and (Test-Path -LiteralPath $script:ShadowLink)) {
        Write-Log "Removing shadow copy mount point '$($script:ShadowLink)'."
        # cmd rmdir removes the directory symlink without touching the target
        cmd /c rmdir "$script:ShadowLink" | Out-Null
    }
    if ($script:ShadowCopy) {
        Write-Log "Deleting VSS snapshot $($script:ShadowCopy.ID)."
        try { $script:ShadowCopy | Remove-CimInstance } catch { Write-Log "Could not delete snapshot: $_" 'WARN' }
        $script:ShadowCopy = $null
    }
}

# ---------------------------------------------------------------------------
# 1. Resolve and validate source / target disks
# ---------------------------------------------------------------------------

Write-Log "Log file: $LogPath"
Write-Log "=== OS disk clone starting ==="

$systemDriveLetter = $env:SystemDrive.TrimEnd(':')
$osPartition = Get-Partition -DriveLetter $systemDriveLetter

if ($SourceDiskNumber -lt 0) {
    $SourceDiskNumber = $osPartition.DiskNumber
    Write-Log "Auto-detected source disk: $SourceDiskNumber (hosts $($env:SystemDrive))."
}

if ($SourceDiskNumber -eq $TargetDiskNumber) {
    throw "Source and target are the same disk ($SourceDiskNumber)."
}

$sourceDisk = Get-Disk -Number $SourceDiskNumber
$targetDisk = Get-Disk -Number $TargetDiskNumber

if ($sourceDisk.PartitionStyle -ne 'GPT') {
    throw ("Source disk $SourceDiskNumber is $($sourceDisk.PartitionStyle), not GPT. " +
           "This script only supports UEFI/GPT systems. For a legacy MBR/BIOS disk, " +
           "use imaging media (e.g. a WinPE-based tool) instead.")
}

# Never allow the disk we're booted from to be the wipe target.
if ($targetDisk.IsBoot -or $targetDisk.IsSystem -or $osPartition.DiskNumber -eq $TargetDiskNumber) {
    throw "Target disk $TargetDiskNumber contains the running operating system. Refusing to erase it."
}

if ($targetDisk.IsOffline) {
    Write-Log "Target disk is offline; bringing it online."
    Set-Disk -Number $TargetDiskNumber -IsOffline $false
}
if ($targetDisk.IsReadOnly) {
    Write-Log "Target disk is read-only; clearing the read-only flag."
    Set-Disk -Number $TargetDiskNumber -IsReadOnly $false
}

# Capacity check: everything we copy must fit on the target.
$sourceEsp = Get-Partition -DiskNumber $SourceDiskNumber |
    Where-Object { $_.GptType -eq '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}' } |
    Select-Object -First 1
if (-not $sourceEsp) {
    throw "No EFI System Partition found on source disk $SourceDiskNumber. Is this really the OS disk?"
}

$osVolume  = Get-Volume -DriveLetter $systemDriveLetter
$usedBytes = [uint64]($osVolume.Size - $osVolume.SizeRemaining)
$espSize   = [uint64][math]::Max($sourceEsp.Size, 260MB)
$overhead  = [uint64]2GB   # MSR, alignment, NTFS metadata, copy-time growth headroom
$required  = $usedBytes + $espSize + $overhead

if ([uint64]$targetDisk.Size -lt $required) {
    throw ("Target disk is too small: {0} available, ~{1} required ({2} of OS data + boot partitions + headroom)." -f
        (Format-Size $targetDisk.Size), (Format-Size $required), (Format-Size $usedBytes))
}

# BitLocker warning (module is absent on some SKUs; ignore if so)
try {
    $blv = Get-BitLockerVolume -MountPoint $env:SystemDrive -ErrorAction Stop
    if ($blv.ProtectionStatus -eq 'On') {
        Write-Log "Source volume is BitLocker-protected. The clone will be UNENCRYPTED; re-enable BitLocker on the target after first boot." 'WARN'
    }
} catch { }

Write-Log ("Source: disk {0} '{1}' ({2}), OS data in use: {3}" -f
    $SourceDiskNumber, $sourceDisk.FriendlyName, (Format-Size $sourceDisk.Size), (Format-Size $usedBytes))
Write-Log ("Target: disk {0} '{1}' ({2})" -f
    $TargetDiskNumber, $targetDisk.FriendlyName, (Format-Size $targetDisk.Size))

# ---------------------------------------------------------------------------
# 2. Confirmation — the target disk is about to be destroyed
# ---------------------------------------------------------------------------

if (-not $Force) {
    Write-Host ""
    Write-Host "ALL DATA ON DISK $TargetDiskNumber ('$($targetDisk.FriendlyName)') WILL BE PERMANENTLY ERASED." -ForegroundColor Red
    $answer = Read-Host "Type 'ERASE $TargetDiskNumber' to continue"
    if ($answer -cne "ERASE $TargetDiskNumber") {
        Write-Log "Confirmation not given; aborting with no changes made." 'WARN'
        return
    }
}

try {
    # -----------------------------------------------------------------------
    # 3. Wipe target and create UEFI/GPT layout
    # -----------------------------------------------------------------------

    Write-Log "Wiping target disk $TargetDiskNumber."
    Clear-Disk -Number $TargetDiskNumber -RemoveData -RemoveOEM -Confirm:$false
    Initialize-Disk -Number $TargetDiskNumber -PartitionStyle GPT

    $efiLetter = Get-FreeDriveLetter
    $osLetter  = Get-FreeDriveLetter -Exclude $efiLetter
    $script:TempLetters = @($efiLetter, $osLetter)

    Write-Log "Creating EFI System Partition ($(Format-Size $espSize))."
    # Created as a basic data partition first: Format-Volume refuses to touch a
    # partition that is already typed as ESP, so format, then retype.
    $efiPart = New-Partition -DiskNumber $TargetDiskNumber -Size $espSize -DriveLetter $efiLetter
    Format-Volume -DriveLetter $efiLetter -FileSystem FAT32 -NewFileSystemLabel 'SYSTEM' -Confirm:$false | Out-Null
    $efiPart | Set-Partition -GptType '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}'

    Write-Log "Creating Microsoft Reserved partition (16 MB)."
    New-Partition -DiskNumber $TargetDiskNumber -Size 16MB `
        -GptType '{e3c9e316-0b5c-4db8-817d-f92df00215ae}' | Out-Null

    Write-Log "Creating OS partition (remaining space, NTFS)."
    $osPart = New-Partition -DiskNumber $TargetDiskNumber -UseMaximumSize -DriveLetter $osLetter
    Format-Volume -DriveLetter $osLetter -FileSystem NTFS `
        -NewFileSystemLabel $(if ($osVolume.FileSystemLabel) { $osVolume.FileSystemLabel } else { 'Windows' }) `
        -Confirm:$false | Out-Null
    Write-Log "Target layout ready: EFI=$($efiLetter):, OS=$($osLetter):." 'OK'

    # -----------------------------------------------------------------------
    # 4. VSS snapshot of the running OS volume
    # -----------------------------------------------------------------------

    Write-Log "Creating VSS snapshot of $($env:SystemDrive)\ for a crash-consistent copy."
    $result = Invoke-CimMethod -ClassName Win32_ShadowCopy -MethodName Create `
        -Arguments @{ Volume = "$($env:SystemDrive)\"; Context = 'ClientAccessible' }
    if ($result.ReturnValue -ne 0) {
        throw "VSS snapshot creation failed (Win32_ShadowCopy.Create returned $($result.ReturnValue))."
    }
    $script:ShadowCopy = Get-CimInstance Win32_ShadowCopy | Where-Object ID -eq $result.ShadowID
    $shadowDevice = $script:ShadowCopy.DeviceObject   # \\?\GLOBALROOT\Device\HarddiskVolumeShadowCopyN

    # robocopy can't address the shadow device directly; expose it via a directory symlink.
    $script:ShadowLink = Join-Path $env:TEMP ("osclone_shadow_" + [guid]::NewGuid().ToString('N'))
    cmd /c mklink /d "$script:ShadowLink" "$shadowDevice\" | Out-Null
    if (-not (Test-Path -LiteralPath $script:ShadowLink)) {
        throw "Failed to create symlink to the VSS snapshot."
    }
    Write-Log "Snapshot mounted at $script:ShadowLink." 'OK'

    # -----------------------------------------------------------------------
    # 5. Mirror the OS volume to the target partition
    # -----------------------------------------------------------------------

    Write-Log "Copying OS volume with robocopy (this is the long part)..."
    $robocopyLog = "$LogPath.robocopy.txt"
    $roboArgs = @(
        "$script:ShadowLink", "$($osLetter):\",
        '/MIR',                     # exact mirror of the snapshot
        '/COPYALL',                 # data, attributes, timestamps, ACLs, owner, audit info
        '/DCOPY:DAT',               # directory data, attributes, timestamps
        '/B',                       # backup mode - reads files regardless of ACLs
        '/SL',                      # copy symbolic links as links, not their targets
        '/XJ',                      # skip junction points (avoids recursion loops)
        '/R:1', '/W:1',             # one quick retry; the snapshot is static anyway
        '/MT:16',                   # multithreaded copy
        '/XF', 'pagefile.sys', 'swapfile.sys', 'hiberfil.sys',
        '/XD', "$script:ShadowLink\System Volume Information", "$script:ShadowLink\`$Recycle.Bin",
        '/NP', '/NDL', '/NFL',      # keep the log readable
        "/LOG:$robocopyLog", '/TEE'
    )
    & robocopy.exe @roboArgs
    $rc = $LASTEXITCODE
    # Robocopy: 0-7 = success (bitmask of copied/extra/mismatched), >=8 = failure
    if ($rc -ge 8) {
        throw "robocopy failed with exit code $rc. See $robocopyLog for details."
    }
    Write-Log "File copy complete (robocopy exit code $rc)." 'OK'

    # -----------------------------------------------------------------------
    # 6. Make the target bootable
    # -----------------------------------------------------------------------

    Write-Log "Writing UEFI boot files with bcdboot."
    $bcdOut = & bcdboot.exe "$($osLetter):\Windows" /s "$($efiLetter):" /f UEFI 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "bcdboot failed (exit $LASTEXITCODE): $bcdOut"
    }
    Write-Log "Boot files created on $($efiLetter): ." 'OK'

    # -----------------------------------------------------------------------
    # 7. Cleanup and hand-off
    # -----------------------------------------------------------------------

    Invoke-Cleanup

    Write-Log "Removing temporary drive letters from the target partitions."
    Remove-PartitionAccessPath -DiskNumber $TargetDiskNumber -PartitionNumber $efiPart.PartitionNumber `
        -AccessPath "$($efiLetter):" -ErrorAction SilentlyContinue
    Remove-PartitionAccessPath -DiskNumber $TargetDiskNumber -PartitionNumber $osPart.PartitionNumber `
        -AccessPath "$($osLetter):" -ErrorAction SilentlyContinue

    Write-Log "=== Clone finished successfully ===" 'OK'
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Shut down the machine."
    Write-Host "  2. Swap the disks, or select disk $TargetDiskNumber in the firmware (UEFI) boot menu."
    Write-Host "  3. Boot - the clone runs independently of the original disk."
    Write-Host "  Notes: the WinRE recovery partition was not cloned (run 'reagentc /enable' to rebuild it),"
    Write-Host "         and if the source used BitLocker, re-enable it on the clone."
}
catch {
    Write-Log "FAILED: $($_.Exception.Message)" 'ERROR'
    Invoke-Cleanup
    Write-Log "The SOURCE disk was not modified. The target disk may be left partially written." 'WARN'
    throw
}
