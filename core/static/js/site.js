// Client-side filtering for product cards by name or SKU
(function(){
  var searchInput = document.querySelector('[data-action="filter-products"]');
  if(searchInput){
    var container = document.querySelector('[data-product-list]');
    if(!container) return;
    var items = Array.prototype.slice.call(container.querySelectorAll('[data-product-item]'));
    searchInput.addEventListener('input', function(){
      var q = (this.value || '').toLowerCase().trim();
      items.forEach(function(el){
        var name = (el.getAttribute('data-name')||'').toLowerCase();
        var sku = (el.getAttribute('data-sku')||'').toLowerCase();
        var match = !q || name.indexOf(q) !== -1 || sku.indexOf(q) !== -1;
        el.style.display = match ? '' : 'none';
      });
    });
  }
})();

// File input enhancement: show selected file name
(function(){
  document.addEventListener('change', function(e){
    var input = e.target;
    if(input && input.matches('input[type="file"]')){
      var label = input.closest('.mb-3, .form-group')?.querySelector('[data-file-name]');
      if(label){
        var name = input.files && input.files.length ? input.files[0].name : 'No file chosen';
        label.textContent = name;
      }
    }
  });
})();

