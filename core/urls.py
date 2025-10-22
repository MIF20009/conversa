from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.owner_dashboard, name='owner_dashboard'),
    path('business/<int:business_id>/products/', views.product_list, name='product_list'),
    path('business/<int:business_id>/products/create/', views.product_create, name='product_create'),
    path('business/<int:business_id>/products/<int:product_id>/edit/', views.product_edit, name='product_edit'),
    path('business/<int:business_id>/products/<int:product_id>/', views.product_detail, name='product_detail'),
    path('business/<int:business_id>/products/<int:product_id>/delete/', views.product_delete, name='product_delete'),
    
    # Category management URLs
    path('business/<int:business_id>/categories/', views.category_list, name='category_list'),
    path('business/<int:business_id>/categories/create/', views.category_create, name='category_create'),
    path('business/<int:business_id>/categories/<int:category_id>/delete/', views.category_delete, name='category_delete'),
    path('business/<int:business_id>/products/import/', views.product_import_excel, name='product_import'),
    
    # Instagram Integration URLs
    path('instagram/connect/<int:business_id>/', views.instagram_connect, name='instagram_connect'),
    path('instagram/callback/<int:business_id>/', views.instagram_callback, name='instagram_callback'),
    path('webhook/instagram/', views.instagram_webhook, name='instagram_webhook'),
]