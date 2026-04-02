from django.contrib import admin
from .models import CustomUser, StripeProduct, Payment, UserSubscription, OTPVerification

admin.site.register(CustomUser)
admin.site.register(StripeProduct)
admin.site.register(Payment)
admin.site.register(UserSubscription)
admin.site.register(OTPVerification)