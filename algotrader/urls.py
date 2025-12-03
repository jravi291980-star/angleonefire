from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # This connects the root URL to your tradeapp
    path('', include('tradeapp.urls')),
]