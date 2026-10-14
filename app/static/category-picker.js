/* Shared progressive enhancement for onboarding and settings. */
document.querySelectorAll('[data-category-picker]').forEach(function (picker) {
  var form = picker.closest('form');
  var panel = picker.querySelector('details');
  var search = picker.querySelector('input[type="search"]');
  var subject = picker.querySelector('select');
  var options = Array.from(picker.querySelectorAll('.category-option'));
  var selectedList = picker.querySelector('[data-selected-categories]');
  var count = picker.querySelector('[data-selection-count]');
  var note = picker.querySelector('[data-selection-note]');
  var resultCount = picker.querySelector('[data-result-count]');
  var max = Number(picker.dataset.max);

  picker.querySelector('.picker-filters').hidden = false;
  resultCount.hidden = false;
  panel.open = panel.dataset.defaultOpen === 'true';

  function updateSelection() {
    var selected = options.filter(function (option) { return option.querySelector('input').checked; });
    count.textContent = selected.length + ' of ' + max + ' selected';
    note.textContent = selected.length >= max
      ? 'You have selected ' + max + ' categories. Remove one to choose another.'
      : 'Choose between 1 and ' + max + ' categories.';
    form.querySelector('[data-save-categories]').disabled = selected.length === 0;
    options.forEach(function (option) {
      var checkbox = option.querySelector('input');
      checkbox.disabled = selected.length >= max && !checkbox.checked;
    });
    selectedList.replaceChildren();
    selected.forEach(function (option) {
      var slug = option.querySelector('input').value;
      var item = document.createElement('li');
      var code = document.createElement('span');
      var remove = document.createElement('button');
      item.append(document.createTextNode(option.dataset.name + ' '));
      code.className = 'category-code';
      code.textContent = slug;
      remove.type = 'button';
      remove.dataset.remove = slug;
      remove.setAttribute('aria-label', 'Remove ' + option.dataset.name + ' (' + slug + ')');
      remove.textContent = '×';
      item.append(code, remove);
      selectedList.append(item);
    });
  }

  function filterOptions() {
    var query = search.value.trim().toLowerCase();
    var visible = 0;
    picker.querySelectorAll('.archive-group').forEach(function (group) {
      var groupVisible = 0;
      group.querySelectorAll('.category-option').forEach(function (option) {
        option.hidden = Boolean((subject.value && subject.value !== group.dataset.archive)
          || (query && !option.dataset.search.includes(query)));
        if (!option.hidden) groupVisible++;
      });
      group.hidden = groupVisible === 0;
      visible += groupVisible;
    });
    resultCount.textContent = visible + (visible === 1 ? ' category' : ' categories') + ' shown';
    picker.querySelector('[data-no-results]').hidden = visible !== 0;
  }

  picker.addEventListener('change', function (event) {
    if (event.target.name === 'slugs') updateSelection();
  });
  selectedList.addEventListener('click', function (event) {
    var button = event.target.closest('button[data-remove]');
    if (!button) return;
    var checkbox = options.map(function (option) { return option.querySelector('input'); })
      .find(function (input) { return input.value === button.dataset.remove; });
    checkbox.checked = false;
    updateSelection();
    // The activated button was removed; keep keyboard focus within the picker.
    var next = selectedList.querySelector('button');
    (next || picker.querySelector('summary')).focus();
  });
  search.addEventListener('input', filterOptions);
  // Enter in search should not accidentally save an unfinished selection.
  search.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') event.preventDefault();
  });
  subject.addEventListener('change', filterOptions);
  panel.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      panel.open = false;
      panel.querySelector('summary').focus();
    }
  });
  updateSelection();
  filterOptions();
});
