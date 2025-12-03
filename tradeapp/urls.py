from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # 1. Homepage Redirects to Dashboard (which redirects to Login if needed)
    path('', views.dashboard, name='home'),
    
    # 2. Main Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # 3. Actions
    path('save-settings/', views.save_settings, name='save_settings'),
    path('save-creds/', views.save_credentials, name='save_credentials'),
    path('callback/', views.angel_callback, name='angel_callback'),
    
    # 4. Authentication (CRITICAL)
    path('login/', auth_views.LoginView.as_view(template_name='tradeapp/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),
]