document.addEventListener('DOMContentLoaded', function () {
  var sb = document.querySelector('.sidebar'), mb = document.querySelector('.menu-btn');
  if (mb && sb) {
    mb.addEventListener('click', function () { sb.classList.toggle('open'); });
    document.addEventListener('click', function (e) {
      if (sb.classList.contains('open') && !sb.contains(e.target) && !mb.contains(e.target)) sb.classList.remove('open');
    });
  }
  document.querySelectorAll('form[data-confirm]').forEach(function (f) {
    f.addEventListener('submit', function (e) { if (!confirm(f.dataset.confirm)) e.preventDefault(); });
  });
  setTimeout(function () {
    document.querySelectorAll('.flash.success').forEach(function (el) {
      el.style.opacity = '0'; setTimeout(function () { el.remove(); }, 500);
    });
  }, 4500);
});
