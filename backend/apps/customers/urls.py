from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.customers import views

app_name = 'customers'

router = DefaultRouter()
router.register(r'staff', views.StaffViewSet, basename='staff')
router.register(r'subscribers', views.SubscriberViewSet, basename='subscribers')

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('profile/', views.profile, name='profile'),
    path('profile/update/', views.update_profile, name='update_profile'),
    path('', include(router.urls)),
]
