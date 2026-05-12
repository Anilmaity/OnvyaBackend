from django.contrib import admin
from apps.invoicing.models import Invoice, InvoiceLineItem, InvoiceCounter

admin.site.register(Invoice)
admin.site.register(InvoiceLineItem)
admin.site.register(InvoiceCounter)
