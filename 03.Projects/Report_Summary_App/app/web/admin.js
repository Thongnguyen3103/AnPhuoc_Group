const ACTION_LABELS = {
  login: 'Đăng nhập', login_failed: 'Đăng nhập sai', logout: 'Đăng xuất', view_report: 'Xem báo cáo',
  'password.change': 'Đổi mật khẩu', 'user.create': 'Tạo người dùng', 'user.update': 'Sửa người dùng',
  'user.reset_password': 'Cấp lại mật khẩu', 'snapshot.import': 'Nạp dữ liệu', 'snapshot.activate': 'Đổi bản dữ liệu',
};
let ME = null;

document.getElementById('nav-logout').addEventListener('click', logout);
document.querySelectorAll('.ap-tab').forEach(btn => btn.addEventListener('click', () => {
  document.querySelectorAll('.ap-tab').forEach(b => b.classList.toggle('active', b === btn));
  document.querySelectorAll('.ap-panel').forEach(p => p.classList.toggle('active', p.id === `panel-${btn.dataset.tab}`));
  ({ users: loadUsers, data: loadSnapshots, audit: loadAudit })[btn.dataset.tab]();
}));

// ---------------- Người dùng ----------------
function secretNote(username, pw) {
  return `Mật khẩu tạm của ${username}: ` + pw + ' — gửi riêng cho người dùng, chỉ hiện 1 lần.';
}

async function loadUsers() {
  const { users } = await api('/api/admin/users');
  document.getElementById('user-count').textContent = `(${users.length})`;
  document.getElementById('users-tbody').innerHTML = users.map(u => `
    <tr>
      <td><strong>${escapeHtml(u.username)}</strong>${u.id === ME.id ? ' <span class="ap-pill gold">bạn</span>' : ''}</td>
      <td>${escapeHtml(u.full_name) || '—'}</td>
      <td><span class="ap-pill ${u.role === 'admin' ? 'gold' : ''}">${u.role === 'admin' ? 'Quản trị' : 'Người xem'}</span></td>
      <td>${u.is_active ? '<span class="ap-pill green">Hoạt động</span>' : '<span class="ap-pill red">Đã khóa</span>'}
          ${u.must_change_password && u.is_active ? '<span class="ap-pill">chờ đổi MK</span>' : ''}</td>
      <td>${fmtTime(u.last_login_at)}</td>
      <td class="ap-actions">
        ${u.id === ME.id ? '' : `
          <button class="ap-btn sm ghost" data-act="role" data-id="${u.id}" data-role="${u.role}">${u.role === 'admin' ? 'Hạ thành Người xem' : 'Nâng Quản trị'}</button>
          <button class="ap-btn sm ghost" data-act="reset" data-id="${u.id}" data-name="${escapeHtml(u.username)}">Cấp lại MK</button>
          <button class="ap-btn sm ${u.is_active ? 'danger' : 'ghost'}" data-act="active" data-id="${u.id}" data-active="${u.is_active ? 1 : 0}">${u.is_active ? 'Khóa' : 'Mở khóa'}</button>`}
      </td>
    </tr>`).join('');
}

document.getElementById('users-tbody').addEventListener('click', async (e) => {
  const b = e.target.closest('button[data-act]');
  if (!b) return;
  const msg = document.getElementById('user-msg');
  const id = Number(b.dataset.id);
  try {
    if (b.dataset.act === 'role') {
      await api(`/api/admin/users/${id}`, { method: 'PATCH', body: { role: b.dataset.role === 'admin' ? 'viewer' : 'admin' } });
      showMsg(msg, 'Đã đổi vai trò.', 'ok');
    } else if (b.dataset.act === 'active') {
      const activate = b.dataset.active !== '1';
      if (!activate && !confirm('Khóa tài khoản này? Người dùng sẽ bị đăng xuất ngay.')) return;
      await api(`/api/admin/users/${id}`, { method: 'PATCH', body: { is_active: activate } });
      showMsg(msg, activate ? 'Đã mở khóa.' : 'Đã khóa tài khoản.', 'ok');
    } else if (b.dataset.act === 'reset') {
      if (!confirm(`Cấp lại mật khẩu cho ${b.dataset.name}? Mật khẩu cũ sẽ hết hiệu lực.`)) return;
      const r = await api(`/api/admin/users/${id}/reset-password`, { method: 'POST' });
      showMsg(msg, secretNote(r.user.username, r.temp_password), 'ok');
    }
    await loadUsers();
  } catch (err) { showMsg(msg, err.message); }
});

document.getElementById('user-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = document.getElementById('user-msg');
  try {
    const r = await api('/api/admin/users', {
      method: 'POST',
      body: {
        username: document.getElementById('nu-username').value.trim(),
        full_name: document.getElementById('nu-fullname').value.trim(),
        role: document.getElementById('nu-role').value,
      },
    });
    showMsg(msg, secretNote(r.user.username, r.temp_password), 'ok');
    e.target.reset();
    await loadUsers();
  } catch (err) {
    showMsg(msg, err.message.startsWith('Dữ liệu nhập') ? 'Tên đăng nhập 3–32 ký tự: chữ, số, dấu . _ -' : err.message);
  }
});

// ---------------- Dữ liệu ----------------
function fmtMB(b) { return b ? (b / 1048576).toFixed(2) + ' MB' : '—'; }

async function loadSnapshots() {
  const { snapshots, source } = await api('/api/admin/snapshots');
  const src = document.getElementById('source-info');
  if (!source) src.textContent = 'Chưa thấy bản build nào trong thư mục nguồn.';
  else if (source.error) src.textContent = source.error;
  else src.innerHTML = `Kỳ <strong>${escapeHtml(source.ref && source.ref.label)}</strong> · build lúc <strong>${escapeHtml(source.built)}</strong> · ${fmtMB(source.payload_size)} · ${(source.sku_count || 0).toLocaleString('vi-VN')} SKU`;
  document.getElementById('snap-tbody').innerHTML = snapshots.map(s => `
    <tr>
      <td>${s.id}</td>
      <td><strong>${escapeHtml(s.ref_label)}</strong></td>
      <td>${escapeHtml(s.built_at)}</td>
      <td>${fmtTime(s.imported_at)}</td>
      <td class="num">${fmtMB(s.size_bytes)}</td>
      <td class="num">${(s.sku_count || 0).toLocaleString('vi-VN')}</td>
      <td>${s.is_active ? '<span class="ap-pill green">Đang dùng</span>' : ''}</td>
      <td>${s.is_active ? '' : `<button class="ap-btn sm ghost" data-snap="${s.id}">Dùng bản này</button>`}</td>
    </tr>`).join('') || '<tr><td colspan="8" class="ap-muted">Chưa có dữ liệu.</td></tr>';
}

document.getElementById('snap-tbody').addEventListener('click', async (e) => {
  const b = e.target.closest('button[data-snap]');
  if (!b) return;
  const msg = document.getElementById('data-msg');
  if (!confirm(`Chuyển mọi người sang bản dữ liệu #${b.dataset.snap}?`)) return;
  try {
    await api(`/api/admin/snapshots/${b.dataset.snap}/activate`, { method: 'POST' });
    showMsg(msg, `Đã chuyển sang bản #${b.dataset.snap}.`, 'ok');
    await loadSnapshots();
  } catch (err) { showMsg(msg, err.message); }
});

document.getElementById('btn-import').addEventListener('click', async (e) => {
  const msg = document.getElementById('data-msg');
  e.target.disabled = true;
  try {
    const r = await api('/api/admin/snapshots/import', { method: 'POST' });
    showMsg(msg, r.created ? `Đã nạp bản #${r.snapshot.id} (${r.snapshot.ref_label}).` : 'Bản build mới nhất đã được nạp trước đó.', 'ok');
    await loadSnapshots();
  } catch (err) { showMsg(msg, err.message); }
  finally { e.target.disabled = false; }
});

// ---------------- Nhật ký ----------------
async function loadAudit() {
  const { items } = await api('/api/admin/audit?limit=200');
  document.getElementById('audit-tbody').innerHTML = items.map(a => `
    <tr>
      <td>${fmtTime(a.at)}</td>
      <td>${escapeHtml(a.username) || '—'}</td>
      <td><span class="ap-pill ${a.action === 'login_failed' ? 'red' : ''}">${escapeHtml(ACTION_LABELS[a.action] || a.action)}</span></td>
      <td>${escapeHtml(a.detail)}</td>
      <td>${escapeHtml(a.ip)}</td>
    </tr>`).join('') || '<tr><td colspan="5" class="ap-muted">Chưa có hoạt động.</td></tr>';
}

(async () => {
  ({ user: ME } = await api('/api/auth/me'));
  await loadUsers();
})();
