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

    class Meta:
        model = NotificationSettings
        fields = [
            'at_username', 'at_api_key', 'at_sender_id', 'at_environment', 'at_api_key_is_set',
            'whatsapp_enabled', 'whatsapp_sender_number', 'whatsapp_provider', 'whatsapp_at_number',
            'telegram_bot_token', 'telegram_webhook_secret', 'telegram_bot_username',
            'telegram_bot_token_is_set', 'telegram_webhook_secret_is_set',
            'staff_alert_phone', 'staff_alert_channel', 'staff_alert_email', 'confirmation_service_types',
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
