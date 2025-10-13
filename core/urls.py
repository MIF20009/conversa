from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.owner_dashboard, name='owner_dashboard'),
    path('business/<int:business_id>/products/', views.product_list, name='product_list'),
    path('business/<int:business_id>/products/create/', views.product_create, name='product_create'),
    path('business/<int:business_id>/products/<int:product_id>/edit/', views.product_edit, name='product_edit'),
    path('business/<int:business_id>/products/import/', views.product_import_excel, name='product_import'),
]