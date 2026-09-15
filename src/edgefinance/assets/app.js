document.querySelectorAll('[data-filter]').forEach(input => {
  input.addEventListener('input', () => {
    const term = input.value.toLocaleLowerCase().trim();
    document.querySelectorAll('[data-searchable]').forEach(row => {
      row.hidden = !row.textContent.toLocaleLowerCase().includes(term);
    });
  });
});
document.querySelectorAll('[data-print]').forEach(button => button.addEventListener('click', () => window.print()));
