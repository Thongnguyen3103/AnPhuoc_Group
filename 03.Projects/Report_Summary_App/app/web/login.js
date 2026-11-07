document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = document.getElementById('msg');
  const btn = document.getElementById('btn-login');
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;
  if (!username || !password) { showMsg(msg, 'Nhập tên đăng nhập và mật khẩu.'); return; }
  hideMsg(msg);
  btn.disabled = true;
  btn.textContent = 'Đang đăng nhập...';
  try {
    const { user } = await api('/api/auth/login', { method: 'POST', body: { username, password } });
    window.location.href = user.must_change_password ? '/account?first=1' : '/';
  } catch (err) {
    showMsg(msg, err.message);
    document.getElementById('password').select();
  } finally {
    btn.disabled = false;
    btn.textContent = 'Đăng nhập';
  }
});
