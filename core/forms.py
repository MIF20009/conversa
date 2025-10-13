from django import forms
from .models import Product
import json

class ProductForm(forms.ModelForm):
    # User-friendly metadata fields
    sizes = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g., S, M, L, XL',
            'class': 'form-control'
        }),
        help_text="Enter sizes separated by commas"
    )
    
    colors = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g., Red, Blue, Green',
            'class': 'form-control'
        }),
        help_text="Enter colors separated by commas"
    )
    
    material = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g., Cotton, Leather, Metal',
            'class': 'form-control'
        }),
        help_text="Material or fabric type"
    )
    
    weight = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g., 250g, 1kg',
            'class': 'form-control'
        }),
        help_text="Product weight"
    )
    
    dimensions = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g., 10x15x5cm',
            'class': 'form-control'
        }),
        help_text="Product dimensions"
    )
    
    brand = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g., Nike, Apple, Samsung',
            'class': 'form-control'
        }),
        help_text="Product brand"
    )
    
    category = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g., Electronics, Clothing, Books',
            'class': 'form-control'
        }),
        help_text="Product category"
    )
    
    tags = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g., new, sale, popular',
            'class': 'form-control'
        }),
        help_text="Tags separated by commas"
    )

    class Meta:
        model = Product
        fields = ['sku','name','description','price_usd','price_lbp','stock','image','active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'price_usd': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'price_lbp': forms.NumberInput(attrs={'class': 'form-control'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate metadata fields from existing JSON data
        if self.instance and self.instance.metadata:
            try:
                metadata = self.instance.metadata
                if isinstance(metadata, dict):
                    self.fields['sizes'].initial = ', '.join(metadata.get('sizes', []))
                    self.fields['colors'].initial = ', '.join(metadata.get('colors', []))
                    self.fields['material'].initial = metadata.get('material', '')
                    self.fields['weight'].initial = metadata.get('weight', '')
                    self.fields['dimensions'].initial = metadata.get('dimensions', '')
                    self.fields['brand'].initial = metadata.get('brand', '')
                    self.fields['category'].initial = metadata.get('category', '')
                    self.fields['tags'].initial = ', '.join(metadata.get('tags', []))
            except (json.JSONDecodeError, TypeError):
                pass

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Convert form fields to JSON metadata
        metadata = {}
        
        # Process comma-separated fields
        sizes = [s.strip() for s in self.cleaned_data.get('sizes', '').split(',') if s.strip()]
        colors = [c.strip() for c in self.cleaned_data.get('colors', '').split(',') if c.strip()]
        tags = [t.strip() for t in self.cleaned_data.get('tags', '').split(',') if t.strip()]
        
        if sizes:
            metadata['sizes'] = sizes
        if colors:
            metadata['colors'] = colors
        if tags:
            metadata['tags'] = tags
            
        # Process single-value fields
        for field in ['material', 'weight', 'dimensions', 'brand', 'category']:
            value = self.cleaned_data.get(field, '').strip()
            if value:
                metadata[field] = value
        
        instance.metadata = metadata if metadata else None
        
        if commit:
            instance.save()
        return instance

class ExcelUploadForm(forms.Form):
    file = forms.FileField(
        help_text="Upload an Excel (.xlsx) file. Required columns: name, price_usd. Optional columns: sku, description, price_lbp, stock",
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )
