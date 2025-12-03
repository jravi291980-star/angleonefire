from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # Include the tradeapp URLs
    path('', include('tradeapp.urls')),
]