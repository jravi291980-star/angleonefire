from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('save-creds/', views.save_credentials, name='save_credentials'),
    path('callback/', views.angel_callback, name='angel_callback'),
    path('square-off/<int:trade_id>/', views.square_off, name='square_off'),
    path('update-tsl/<int:trade_id>/', views.update_tsl, name='update_tsl'),
]