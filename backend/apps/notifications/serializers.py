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

    at_api_key_is_set = serializers.SerializerMethodField()
    telegram_bot_token_is_set = serializers.SerializerMethodField()
    telegram_webhook_secret_is_set = serializers.SerializerMethodField()

    class Meta:
        model = NotificationSettings
        fields = [
            'at_username', 'at_api_key', 'at_sender_id', 'at_environment', 'at_api_key_is_set',
            'whatsapp_enabled', 'whatsapp_sender_number', 'whatsapp_provider', 'whatsapp_at_number',
            'telegram_bot_token', 'telegram_webhook_secret', 'telegram_bot_username',
            'telegram_bot_token_is_set', 'telegram_webhook_secret_is_set',
            'updated_at',
        ]
        read_only_fields = ['updated_at']

    def get_at_api_key_is_set(self, obj):
        return bool(obj.at_api_key)

    def get_telegram_bot_token_is_set(self, obj):
        return bool(obj.telegram_bot_token)

    def get_telegram_webhook_secret_is_set(self, obj):
        return bool(obj.telegram_webhook_secret)

    def update(self, instance, validated_data):
        # Blank-on-submit means "leave unchanged" for secrets specifically --
        # the frontend never has the real value to send back, so an empty
        # string here is "the admin didn't type a new one", not "clear it".
        for field in ('at_api_key', 'telegram_bot_token', 'telegram_webhook_secret'):
            if field in validated_data and not validated_data[field]:
                validated_data.pop(field)
        return super().update(instance, validated_data)
