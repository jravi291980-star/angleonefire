from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Homepage -> Redirects to Dashboard or Login
    path('', views.dashboard, name='home'),
    
    path('dashboard/', views.dashboard, name='dashboard'),
    path('save-settings/', views.save_settings, name='save_settings'),
    path('save-creds/', views.save_credentials, name='save_credentials'),
    path('callback/', views.angel_callback, name='angel_callback'),
    
    # Authentication
    path('login/', auth_views.LoginView.as_view(template_name='tradeapp/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
]