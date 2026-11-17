from rest_framework import serializers

from .models import NotificationSettings


class NotificationSettingsSerializer(serializers.ModelSerializer):
    """
    Encrypted credential fields are write_only and never round-trip the
    decrypted secret back to the frontend -- an `<field>_is_set` boolean
    tells the settings page whether one is already configured, so it can
    show "•••• (set)" instead. An empty value on PATCH means "leave
    unchanged" (see NotificationSettingsView.patch), not "clear".
    """
    at_api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    telegram_bot_token = serializers.CharField(write_only=True, required=False, allow_blank=True)
    telegram_webhook_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    smtp_password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    at_api_key_is_set = serializers.SerializerMethodField()
    telegram_bot_token_is_set = serializers.SerializerMethodField()
    telegram_webhook_secret_is_set = serializers.SerializerMethodField()
    smtp_password_is_set = serializers.SerializerMethodField()
    superadmin_recipients = serializers.SerializerMethodField()
    reminder_schedule = serializers.SerializerMethodField()

    class Meta:
        model = NotificationSettings
        fields = [
            'at_username', 'at_api_key', 'at_sender_id', 'at_environment', 'at_api_key_is_set',
            'whatsapp_enabled', 'whatsapp_sender_number', 'whatsapp_provider', 'whatsapp_at_number',
            'telegram_bot_token', 'telegram_webhook_secret', 'telegram_bot_username',
            'telegram_bot_token_is_set', 'telegram_webhook_secret_is_set',
            'admin_phones', 'admin_emails', 'admin_phone_channels', 'confirmation_service_types', 'admin_event_emails', 'daily_report_enabled', 'confirmation_channels', 'confirmation_sms_fallback', 'reminder_enabled', 'reminder_days_before', 'reminder_every_days', 'reminder_on_expiry_day', 'reminder_hour', 'reminder_service_types', 'reminder_channels', 'reminder_sms_fallback', 'reminder_schedule', 'sales_phones', 'sales_emails', 'expired_followup_enabled', 'expired_followup_hour', 'superadmin_recipients',
            'usage_alerts_enabled', 'usage_alert_thresholds', 'usage_alert_service_types', 'usage_alert_channels', 'daily_fup_notify',
            'email_enabled', 'smtp_provider', 'smtp_host', 'smtp_port', 'smtp_security',
            'smtp_username', 'smtp_password', 'smtp_password_is_set', 'email_from_address', 'email_from_name',
            'updated_at',
        ]
        read_only_fields = ['updated_at']

    def get_at_api_key_is_set(self, obj):
        return bool(obj.at_api_key)

    def get_telegram_bot_token_is_set(self, obj):
        return bool(obj.telegram_bot_token)

    def get_telegram_webhook_secret_is_set(self, obj):
        return bool(obj.telegram_webhook_secret)

    def get_smtp_password_is_set(self, obj):
        return bool(obj.smtp_password)

    def get_superadmin_recipients(self, obj):
        # Superadmin profile emails, which always get admin emails too.
        from apps.notifications.admin_emails import superadmin_emails
        return superadmin_emails()

    def validate_admin_emails(self, value):
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError as DjangoValidationError
        emails = NotificationSettings._split(value)
        bad = []
        for e in emails:
            try:
                validate_email(e)
            except DjangoValidationError:
                bad.append(e)
        if bad:
            raise serializers.ValidationError(f"Not valid email address(es): {', '.join(bad)}")
        return '\n'.join(dict.fromkeys(e.lower() for e in emails))

    def validate_admin_phones(self, value):
        from apps.payments.services.phone_hash import normalize_phone
        phones = NotificationSettings._split(value)
        bad = [p for p in phones if not (normalize_phone(p).isdigit() and len(normalize_phone(p)) == 12)]
        if bad:
            raise serializers.ValidationError(f"Not valid phone number(s): {', '.join(bad)} (use 07XXXXXXXX or 2547XXXXXXXX)")
        from apps.payments.services.phone_hash import fix_bare_phone
        return '\n'.join(dict.fromkeys(fix_bare_phone(p) for p in phones))

    def validate_usage_alert_thresholds(self, value):
        parts = NotificationSettings._split(value)
        try:
            nums = sorted({int(float(p)) for p in parts})
        except ValueError:
            raise serializers.ValidationError('Use whole percentages separated by commas, e.g. 50,75,95')
        if any(n <= 0 or n >= 100 for n in nums):
            raise serializers.ValidationError('Each percentage must be between 1 and 99')
        return ','.join(str(n) for n in nums)

    def validate_sales_emails(self, value):
        return self.validate_admin_emails(value)

    def validate_sales_phones(self, value):
        return self.validate_admin_phones(value)

    def validate_expired_followup_hour(self, value):
        return self.validate_reminder_hour(value)

    def get_reminder_schedule(self, obj):
        # Days before expiry that currently get a reminder, for the settings page.
        return obj.reminder_offsets()

    def validate_reminder_channels(self, value):
        return self.validate_confirmation_channels(value)

    def validate_reminder_days_before(self, value):
        if value > 60:
            raise serializers.ValidationError('At most 60 days before expiry.')
        return value

    def validate_reminder_every_days(self, value):
        if not 1 <= value <= 60:
            raise serializers.ValidationError('Repeat every 1 to 60 days.')
        return value

    def validate_reminder_hour(self, value):
        if value > 23:
            raise serializers.ValidationError('Hour must be 0-23.')
        return value

    def validate_reminder_service_types(self, value):
        types = [t for t in NotificationSettings._split(value) if t in ('pppoe', 'static', 'hotspot')]
        return ','.join(dict.fromkeys(types))

    def validate_confirmation_channels(self, value):
        channels = [c for c in NotificationSettings._split(value) if c in ('sms', 'whatsapp', 'email')]
        if not channels:
            raise serializers.ValidationError('Choose at least one channel for confirmations.')
        return ','.join(dict.fromkeys(channels))

    def validate_admin_phone_channels(self, value):
        channels = [c for c in NotificationSettings._split(value) if c in ('sms', 'whatsapp')]
        return ','.join(dict.fromkeys(channels))

    def validate_at_api_key(self, value):
        # A truncated paste (e.g. the first 9 characters) saved silently
        # and every SMS then failed with a 401. Real keys are long:
        # 'atsk_' + 64 hex for current keys, 64 hex for older ones.
        value = (value or '').strip()
        if value and len(value) < 40:
            raise serializers.ValidationError(
                f"That's only {len(value)} characters -- an Africa's Talking API key is about 70 "
                "(it usually starts with 'atsk_'). Copy the whole key from the dashboard."
            )
        return value

    def validate(self, attrs):
        # The sandbox only works with username 'sandbox' (and never delivers
        # to real phones); a live app never uses that username.
        username = (attrs.get('at_username', self.instance.at_username if self.instance else '') or '').strip()
        env = attrs.get('at_environment', self.instance.at_environment if self.instance else 'sandbox')
        if username and env == 'production' and username == 'sandbox':
            raise serializers.ValidationError({'at_username': "Use your live app's username (not 'sandbox') with Production."})
        if username and env == 'sandbox' and username != 'sandbox':
            raise serializers.ValidationError({'at_environment': "The sandbox only accepts username 'sandbox'. Choose Production for your live app."})
        return attrs

    def update(self, instance, validated_data):
        # Blank-on-submit means "leave unchanged" for secrets specifically --
        # the frontend never has the real value to send back, so an empty
        # string here is "the admin didn't type a new one", not "clear it".
        for field in ('at_api_key', 'telegram_bot_token', 'telegram_webhook_secret', 'smtp_password'):
            if field in validated_data and not validated_data[field]:
                validated_data.pop(field)
        return super().update(instance, validated_data)
