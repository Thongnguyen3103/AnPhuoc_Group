(async () => {
  const first = new URLSearchParams(location.search).has('first');
  document.getElementById('nav-logout').addEventListener('click', logout);
  try {
    const { user } = await api('/api/auth/me');
    document.getElementById('who').textContent = user.full_name ? `${user.full_name} (${user.username})` : user.username;
    if (user.role === 'admin') document.getElementById('nav-admin').hidden = false;
    if (first || user.must_change_password) {
      document.getElementById('pw-sub').insertAdjacentHTML('afterend',
        '<div class="ap-msg show ok" style="margin: 0 0 8px;">Lần đăng nhập đầu: hãy đặt mật khẩu riêng của bạn để tiếp tục.</div>');
      document.getElementById('nav-report').hidden = true;
    }
  } catch (e) { /* api() đã chuyển về /login nếu hết phiên */ }
})();

document.getElementById('pw-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = document.getElementById('msg');
  const btn = document.getElementById('btn-save');
  const current_password = document.getElementById('current').value;
  const new_password = document.getElementById('next').value;
  if (new_password !== document.getElementById('confirm').value) { showMsg(msg, 'Hai lần nhập mật khẩu mới không khớp.'); return; }
  btn.disabled = true;
  try {
    await api('/api/auth/change-password', { method: 'POST', body: { current_password, new_password } });
    showMsg(msg, 'Đã đổi mật khẩu. Đang mở báo cáo...', 'ok');
    setTimeout(() => { window.location.href = '/'; }, 900);
  } catch (err) {
    showMsg(msg, err.message);
  } finally {
    btn.disabled = false;
  }
});
