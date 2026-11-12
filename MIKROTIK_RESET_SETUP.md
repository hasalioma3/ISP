# MikroTik: initial setup after a reset

A reset MikroTik can't be reached by the billing portal: the factory firewall
drops everything arriving on the WAN port (`ether1`), including the RouterOS
API (port 8728) the portal uses. This guide opens just enough access for the
portal to connect. The portal's **Provision** button then does the rest
(bridge, hotspot, PPPoE, pools, DHCP, NAT, login page and profiles).

Tested on RouterOS v7. It works whether the router was reset with or without
the default configuration.

## Before you start

- **Cables:** the uplink (your LAN switch / UniFi) goes into **`ether1`**, and
  your laptop goes into **`ether2`**. `ether2` is the reserved management
  port; provisioning never touches it.
- **Winbox:** open Winbox → **Neighbors** and connect by **MAC address**. That
  works even before the router has an IP. Log in as `admin` with the password
  on the router's sticker (older models have none).
- **Terminal:** click **New Terminal** and paste each block below *including
  its `{ }`*. The braces make the console run the block as one script; without
  them it forgets the variables between lines.

## Step 1: WAN access for the portal

Paste this whole block:

```
{
:local wan "ether1"
:local prefix "ISP Billing - Portal Access"
:local sources {"10.0.0.0/8";"172.16.0.0/12";"192.168.0.0/16"}

/system clock set time-zone-name=Africa/Nairobi

:if ([:len [/interface bridge port find where interface=$wan]] > 0) do={
  /interface bridge port remove [find where interface=$wan]
  :put "ether1 was a bridge port - removed it from the bridge"
}

:if ([:len [/ip dhcp-client find where interface=$wan]] = 0) do={
  /ip dhcp-client add interface=$wan disabled=no comment=($prefix . " (WAN DHCP)")
  :put "Added a DHCP client on ether1"
} else={
  /ip dhcp-client enable [find where interface=$wan]
}

/ip firewall filter remove [find where comment~"^ISP Billing - Portal Access"]
:foreach n in=$sources do={
  :local top [/ip firewall filter find where dynamic=no]
  :if ([:len $top] > 0) do={
    /ip firewall filter add chain=input in-interface=$wan src-address=$n protocol=tcp dst-port=8728,8729,8291,22 action=accept comment=($prefix . " [" . $n . "]") place-before=[:pick $top 0]
  } else={
    /ip firewall filter add chain=input in-interface=$wan src-address=$n protocol=tcp dst-port=8728,8729,8291,22 action=accept comment=($prefix . " [" . $n . "]")
  }
}
:local top [/ip firewall filter find where dynamic=no]
/ip firewall filter add chain=input in-interface=$wan protocol=icmp action=accept comment=($prefix . " (ping)") place-before=[:pick $top 0]

:foreach s in={"api";"winbox";"ssh"} do={
  :do { /ip service set $s disabled=no } on-error={ :put ("Could not enable " . $s . " - enable it in IP > Services") }
}

:delay 5s
:local id [/ip address find where interface=$wan]
:if ([:len $id] = 0) do={
  :put "WARNING: ether1 has no IP yet. Check the cable, wait a few seconds, then run: /ip dhcp-client print"
} else={
  :put ("DONE. Router WAN address (enter this in the portal): " . [/ip address get [:pick $id 0] address])
}
/ip service print where name="api" or name="winbox" or name="ssh"
/ip firewall filter print where comment~"Portal Access"
}
```

**What it does:**
- **Clock:** sets the router's time zone to Africa/Nairobi, so its logs match
  the portal.
- **WAN port:** takes `ether1` out of any bridge and makes sure it gets an
  address by DHCP from your LAN.
- **Firewall:** allows the API (8728, plus 8729 for API over SSL), Winbox
  (8291), SSH (22) and ping, but **only from private addresses (LAN, VPN and
  Teleport) arriving on `ether1`**. The public internet and customers on the
  bridge ports stay blocked. The rules go **above** the factory "drop
  everything not from LAN" rule, otherwise they'd never be reached.
- **Services:** turns on the API, Winbox and SSH services, one at a time.
  Newer RouterOS versions refuse a bulk change that includes telnet.

**Check the output:**
- **The `DONE.` line** gives the WAN address. You'll need it in the portal.
- **Services:** `api`, `winbox` and `ssh` should not have the `X` (disabled)
  flag.
- **Firewall:** the four `ISP Billing - Portal Access` rules should be at the
  top, numbered 0 to 3.

**Safe to run again:** it deletes its own previous rules first, so you never
get duplicates. Its comment ("Portal Access") is deliberately different from
the portal's WAN Management rules, so the **Disable WAN Management Access**
button can never cut the portal off.

### Static WAN address instead of DHCP (optional)

If the uplink doesn't hand out addresses, use this instead of the DHCP client.
Replace the addresses with your own:

```
/ip dhcp-client disable [find where interface="ether1"]
/ip address add address=192.168.58.198/24 interface=ether1
/ip route add dst-address=0.0.0.0/0 gateway=192.168.58.1
/ip dns set servers=8.8.8.8,1.1.1.1
```

## Step 2: a login for the portal (recommended)

Don't give the portal the `admin` login. Replace `CHANGE-ME` with a strong
password, then paste:

```
{
:local pw "CHANGE-ME"
:if ($pw = "CHANGE-ME") do={ :error "Edit the password in the first line first" }
:if ([:len [/user find where name="isp-portal"]] = 0) do={
  /user add name=isp-portal group=full password=$pw
} else={
  /user set [find where name="isp-portal"] group=full password=$pw
}
:put "User isp-portal is ready"
}
```

The portal needs `group=full` because provisioning changes the router's
configuration. If `admin` still has no password, set one too:
`/user set admin password="ANOTHER-STRONG-PASSWORD"`.

## Step 3: give the router a fixed address on your LAN

If the WAN address came from DHCP, reserve it, otherwise it can change and the
portal loses the router. In the UniFi Dream Router, open the MikroTik under
**Client Devices** and turn on **Fixed IP Address**.

## Step 4: finish in the portal

1. **Check from the Pi:** `ping -c 3 <router-wan-ip>` and
   `nc -zv -w 3 <router-wan-ip> 8728`. Both should succeed.
2. **Update the router's details:** on the **MikroTik** page, edit the
   router (or add it). Set **IP address** to the WAN address without the
   `/24`, and enter the `isp-portal` username and password.
3. **Test:** click **Test Connection & List Interfaces**. It should list the
   router's interfaces.
4. **Provision:** click **Provision**. A reset router needs the full setup
   again: bridge, hotspot, PPPoE, pools, DHCP, NAT and login page.
5. **Push your data:** run **Sync Profiles**, then **Sync Users**, to push
   your plans and current customers.
6. **Optional:** if you use them, run **Enable WAN Management Access** and
   **Enable Radio Management VLAN** again.
7. **Status:** the router's status badge should show **Online** within
   about 15 seconds.

## Troubleshooting

- **The `DONE.` line warns that ether1 has no IP:**
  - check the cable;
  - run `/ip dhcp-client print`; the status should be `bound`;
  - check that the uplink port isn't on a VLAN the router doesn't expect.
- **Ping from the Pi fails:** the Pi and the router can't reach each other.
  Check that they're on the same LAN, or that there's a route between their
  subnets. Then check that rules 0 to 3 are the Portal Access rules:
  `/ip firewall filter print`.
- **Ping works but port 8728 doesn't:**
  - run `/ip service print`; `api` must be enabled on port 8728;
  - if it shows an `address` restriction, clear it in
    **IP → Services → api**.
- **Port 8728 works but Test Connection fails:** the username or password in
  the portal doesn't match the router's.
- **Undo this guide:**

  ```
  /ip firewall filter remove [find where comment~"^ISP Billing - Portal Access"]
  /ip dhcp-client remove [find where comment~"^ISP Billing - Portal Access"]
  ```
