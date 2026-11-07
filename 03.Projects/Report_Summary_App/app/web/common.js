// Tiện ích dùng chung cho các trang của Report_Summary_App
async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* không phải JSON */ }
  if (res.status === 401 && !path.startsWith('/api/auth/login')) {
    window.location.href = '/login';
    throw new Error('Phiên đăng nhập đã hết hạn.');
  }
  if (!res.ok) {
    let msg = data && data.detail;
    if (Array.isArray(msg)) msg = 'Dữ liệu nhập chưa hợp lệ: ' + msg.map(d => (d.loc || []).slice(-1)[0]).join(', ');
    throw new Error(msg || `Lỗi máy chủ (${res.status})`);
  }
  return data;
}

function showMsg(el, text, kind = 'err') {
  el.textContent = text;
  el.className = `ap-msg show ${kind}`;
}

function hideMsg(el) { el.className = 'ap-msg'; }

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function fmtTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString('vi-VN', { hour12: false });
}

async function logout() {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch (e) { /* vẫn chuyển trang */ }
  window.location.href = '/login';
}
