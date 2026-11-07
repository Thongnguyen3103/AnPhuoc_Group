// Gắn vào trang báo cáo (chế độ máy chủ): chip người dùng trên header + đổi nhãn "Offline"
(async () => {
  const meta = document.querySelector('.header-meta');
  if (!meta) return;
  meta.querySelectorAll('.meta-badge').forEach(b => {
    if (b.textContent.includes('Offline')) b.textContent = '🌐 Máy chủ nội bộ';
  });
  try {
    const res = await fetch('/api/auth/me', { credentials: 'same-origin' });
    if (res.status === 401) { window.location.href = '/login'; return; }
    const { user } = await res.json();
    const chip = document.createElement('span');
    chip.className = 'meta-badge ap-user-chip';
    const name = document.createElement('strong');
    name.textContent = '👤 ' + (user.full_name || user.username);
    chip.appendChild(name);
    const links = [['/account', 'Đổi mật khẩu']];
    if (user.role === 'admin') links.push(['/admin', 'Quản trị']);
    links.forEach(([href, label]) => {
      const a = document.createElement('a');
      a.href = href;
      a.textContent = label;
      chip.appendChild(a);
    });
    const out = document.createElement('button');
    out.type = 'button';
    out.textContent = 'Đăng xuất';
    out.addEventListener('click', async () => {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
      window.location.href = '/login';
    });
    chip.appendChild(out);
    meta.appendChild(chip);
  } catch (e) {
    console.warn('Không tải được thông tin người dùng', e);
  }
})();
