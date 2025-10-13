from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Business, Product
from .forms import ProductForm, ExcelUploadForm
import pandas as pd
from django.contrib import messages

@login_required
def owner_dashboard(request):
    # show list of businesses owned by user
    businesses = request.user.businesses.all()
    # if multiple businesses show list; else show products
    return render(request, 'core/owner_dashboard.html', {'businesses': businesses})

@login_required
def product_list(request, business_id):
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    products = business.products.all().order_by('-created_at')
    return render(request, 'core/product_list.html', {'business': business, 'products': products})

@login_required
def product_create(request, business_id):
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            p = form.save(commit=False)
            p.business = business
            p.save()
            messages.success(request, 'Product added.')
            return redirect('core:product_list', business_id=business.id)
    else:
        form = ProductForm()
    return render(request, 'core/product_form.html', {'form': form, 'business': business})

@login_required
def product_edit(request, business_id, product_id):
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    product = get_object_or_404(Product, id=product_id, business=business)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated.')
            return redirect('core:product_list', business_id=business.id)
    else:
        form = ProductForm(instance=product)
    return render(request, 'core/product_form.html', {'form': form, 'business': business, 'product': product})

@login_required
def product_import_excel(request, business_id):
    business = get_object_or_404(Business, id=business_id, owner=request.user)
    if request.method == 'POST':
        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            try:
                df = pd.read_excel(file)  # expects columns: sku,name,description,price_usd,price_lbp,stock
            except Exception as e:
                messages.error(request, f'Error reading Excel: {e}')
                return redirect('core:product_list', business_id=business.id)

            created = 0
            errors = []
            
            for index, row in df.iterrows():
                try:
                    # Required fields
                    name = str(row.get('name', '')).strip()
                    if not name or name.lower() in ['nan', 'none', '']:
                        errors.append(f'Row {index + 2}: Name is required')
                        continue
                    
                    price_usd = row.get('price_usd')
                    if pd.isna(price_usd) or price_usd is None:
                        errors.append(f'Row {index + 2}: Price USD is required')
                        continue
                    
                    try:
                        price_usd = float(price_usd)
                        if price_usd < 0:
                            raise ValueError("Price cannot be negative")
                    except (ValueError, TypeError):
                        errors.append(f'Row {index + 2}: Invalid price USD value')
                        continue
                    
                    # Optional fields - handle NaN/None values
                    sku = row.get('sku')
                    if pd.isna(sku) or sku is None or str(sku).strip().lower() in ['nan', 'none', '']:
                        sku = None
                    else:
                        sku = str(sku).strip()
                    
                    description = row.get('description', '')
                    if pd.isna(description) or description is None:
                        description = ''
                    else:
                        description = str(description).strip()
                    
                    price_lbp = row.get('price_lbp')
                    if pd.isna(price_lbp) or price_lbp is None or str(price_lbp).strip().lower() in ['nan', 'none', '']:
                        price_lbp = None
                    else:
                        try:
                            price_lbp = int(float(price_lbp))
                        except (ValueError, TypeError):
                            price_lbp = None
                    
                    stock = row.get('stock', 0)
                    if pd.isna(stock) or stock is None or str(stock).strip().lower() in ['nan', 'none', '']:
                        stock = 0
                    else:
                        try:
                            stock = int(float(stock))
                            if stock < 0:
                                stock = 0
                        except (ValueError, TypeError):
                            stock = 0
                    
                    # Create product
                    Product.objects.create(
                        business=business,
                        sku=sku,
                        name=name,
                        description=description,
                        price_usd=price_usd,
                        price_lbp=price_lbp,
                        stock=stock,
                        active=True
                    )
                    created += 1
                    
                except Exception as e:
                    errors.append(f'Row {index + 2}: {str(e)}')
                    continue
            
            # Show results
            if errors:
                for error in errors[:5]:  # Show first 5 errors
                    messages.error(request, error)
                if len(errors) > 5:
                    messages.warning(request, f'... and {len(errors) - 5} more errors')
            
            if created > 0:
                messages.success(request, f'Successfully imported {created} products.')
            else:
                messages.error(request, 'No products were imported. Please check your Excel file format.')
            return redirect('core:product_list', business_id=business.id)
    else:
        form = ExcelUploadForm()
    return render(request, 'core/product_import.html', {'form': form, 'business': business})


def home(request):
    """Home page - shows landing page for all users"""
    return render(request, 'core/home.html')
