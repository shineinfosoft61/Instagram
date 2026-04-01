"""
URL configuration for instagram project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path
from .views import (
    InstagramDownloadView,
    InstagramPrivateReelDownloadView,
    RegisterView,
    LoginView,
    ForgotPasswordView,
    ResetPasswordView,
    LogoutView,
    DeleteAccountView,
    CreateProductView,
    CreatePaymentIntentView,
    StripeWebhookView,
    PaymentStatusView,
    PlanListView,
    MySubscriptionView,
)

urlpatterns = [
    path('ping', InstagramDownloadView.as_view(), name='ping'),
    path('instagram-download', InstagramDownloadView.as_view(), name='instagram-download'),
    path('instagram-private-reel-download', InstagramPrivateReelDownloadView.as_view(), name='instagram-private-reel-download'),
    path('register', RegisterView.as_view(), name='register'),
    path('login', LoginView.as_view(), name='login'),
    path('forgot-password', ForgotPasswordView.as_view(), name='forgot-password'),
    path('reset-password', ResetPasswordView.as_view(), name='reset-password'),
    path('logout', LogoutView.as_view(), name='logout'),
    path('delete-account', DeleteAccountView.as_view(), name='delete-account'),
    path('create-product', CreateProductView.as_view(), name='create-product'),
    path('create-payment-intent', CreatePaymentIntentView.as_view(), name='create-payment-intent'),
    path('stripe-webhook', StripeWebhookView.as_view(), name='stripe-webhook'),
    path('payment-status/<str:payment_intent_id>', PaymentStatusView.as_view(), name='payment-status'),
    path('plans', PlanListView.as_view(), name='plan-list'),
    path('my-subscription', MySubscriptionView.as_view(), name='my-subscription'),
]
