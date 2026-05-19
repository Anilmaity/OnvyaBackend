from django.contrib import admin

from apps.payments.models import (
    AgencyPaymentAccount,
    DriverBankAccount,
    PaymentStatusEvent,
    PayRun,
    PayRunItem,
)


@admin.register(AgencyPaymentAccount)
class AgencyPaymentAccountAdmin(admin.ModelAdmin):
    list_display = ("agency", "provider", "provider_account_id",
                    "last_known_balance", "is_active")
    readonly_fields = ("last_known_balance", "last_balance_synced_at",
                       "created_at", "updated_at")


@admin.register(DriverBankAccount)
class DriverBankAccountAdmin(admin.ModelAdmin):
    list_display = ("agency", "driver", "account_holder_name",
                    "is_primary", "cop_status")
    search_fields = ("driver__last_name", "account_holder_name")


class PayRunItemInline(admin.TabularInline):
    model = PayRunItem
    extra = 0
    readonly_fields = ("driver", "amount", "status", "provider_payment_id",
                       "paid_at", "failure_reason")


@admin.register(PayRun)
class PayRunAdmin(admin.ModelAdmin):
    list_display = ("agency", "period_start", "period_end", "status",
                    "total_amount", "item_count")
    list_filter = ("status",)
    inlines = [PayRunItemInline]
    readonly_fields = ("provider_batch_id", "idempotency_key",
                       "submitted_at", "approved_at",
                       "created_at", "updated_at")


@admin.register(PaymentStatusEvent)
class PaymentStatusEventAdmin(admin.ModelAdmin):
    list_display = ("agency", "event_type", "item", "payrun", "created_at")
    list_filter = ("event_type",)
    readonly_fields = ("agency", "item", "payrun", "event_type",
                       "provider_event_id", "payload", "created_at", "updated_at")
