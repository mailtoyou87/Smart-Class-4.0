let user=null,classes=[],selected=null;
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,opts={}){
  const r=await fetch('/api'+path,{credentials:'same-origin',...opts,headers:{'X-Smart-Request':'1','Content-Type':'application/json',...(opts.headers||{})}});
  if(!r.ok){let data=await r.json().catch(()=>({}));throw Error(data.detail||'Lỗi kết nối')}
  return r.json();
}
const error=e=>{let el=$('#error');if(el)el.textContent=e.message;else alert(e.message)};
function loginView(){
  $('#app').innerHTML=`<div class="card"><h2>Đăng nhập</h2><form id="login"><label>Tài khoản<input name="username" autocomplete="username" required></label><label>Mật khẩu<input type="password" name="password" autocomplete="current-password" required></label><button>Đăng nhập</button></form><p id="error" class="error"></p></div>`;
  $('#login').onsubmit=async e=>{e.preventDefault();let f=new FormData(e.target);try{user=await api('/login',{method:'POST',body:JSON.stringify(Object.fromEntries(f))});await load()}catch(err){error(err)}};
}
async function load(){
  classes=await api('/classes');selected=classes.some(c=>c.id===selected)?selected:classes[0]?.id;
  if(!selected){if(user.role==='admin'){await adminView();return}$('#app').innerHTML='<div class="card">Tài khoản chưa được phân lớp.</div>';return}
  let [students,notices]=await Promise.all([api('/students?class_id='+selected),api('/notices?class_id='+selected)]);
  $('#app').innerHTML=`<div class="card"><div class="row"><div><strong>${esc(user.name)}</strong> <span class="tag">${esc(user.role)}</span></div><button class="secondary" id="logout">Đăng xuất</button></div><label>Chọn lớp<select id="class">${classes.map(c=>`<option value="${c.id}" ${c.id===selected?'selected':''}>${esc(c.name)} (${esc(c.school_year)})</option>`).join('')}</select></label></div>
  <div class="card"><details><summary>Đổi mật khẩu</summary><form id="changePassword"><label>Mật khẩu hiện tại<input name="current_password" type="password" required></label><label>Mật khẩu mới (tối thiểu 12 ký tự)<input name="new_password" type="password" minlength="12" required></label><button>Đổi mật khẩu</button></form></details></div>
  <div class="card"><h2>Học sinh ${user.role==='parent'?'của gia đình':'trong lớp'}</h2>${students.length?`<table><thead><tr><th>Mã</th><th>Họ tên</th></tr></thead><tbody>${students.map(s=>`<tr><td>${esc(s.code)}</td><td>${esc(s.name)}</td></tr>`).join('')}</tbody></table>`:'Chưa có dữ liệu'}</div>
  ${user.role==='parent'?'':`<div class="card"><h2>Đăng thông báo cho lớp</h2><form id="noticeForm"><label>Tiêu đề<input name="title" maxlength="120" required></label><label>Nội dung<textarea name="body" maxlength="3000" required></textarea></label><button>Đăng thông báo</button></form><p id="error" class="error"></p></div>`}
  <div class="card"><h2>Thông báo lớp</h2>${notices.length?notices.map(n=>`<article style="padding:14px 0;border-bottom:1px solid #eee"><div class="row"><strong>${esc(n.title)}</strong><span class="tag">${esc(n.created_at)}</span></div><p class="notice">${esc(n.body)}</p><small class="muted">Người đăng: ${esc(n.author)}</small>${user.role==='parent'?`<div style="margin-top:10px"><button data-read="${n.id}" ${n.is_read?'disabled':''}>${n.is_read?'✓ Đã đọc':'Xác nhận đã đọc'}</button></div>`:`<div style="margin-top:8px"><button class="secondary" data-count="${n.id}">Xem lượt xác nhận</button> <span id="count-${n.id}"></span></div>`}</article>`).join(''):'Chưa có thông báo'}</div>`;
  if(user.role==='admin'){const nav=document.createElement('div');nav.className='card';nav.innerHTML='<button id="adminPanel">⚙️ Quản trị lớp và tài khoản</button>';$('#app').prepend(nav);$('#adminPanel').onclick=()=>adminView().catch(error)}
  $('#changePassword').onsubmit=async e=>{e.preventDefault();try{await api('/account/change-password',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});alert('Đã đổi mật khẩu. Vui lòng đăng nhập lại.');user=null;loginView()}catch(err){error(err)}};
  $('#class').onchange=e=>{selected=Number(e.target.value);load().catch(error)};
  $('#logout').onclick=async()=>{await api('/logout',{method:'POST'});user=null;loginView()};
  if($('#noticeForm'))$('#noticeForm').onsubmit=async e=>{e.preventDefault();let f=new FormData(e.target);try{await api('/notices',{method:'POST',body:JSON.stringify({class_id:selected,...Object.fromEntries(f)})});await load()}catch(err){error(err)}};
  document.querySelectorAll('[data-read]').forEach(b=>b.onclick=async()=>{try{await api('/notices/'+b.dataset.read+'/read',{method:'POST'});await load()}catch(err){error(err)}});
  document.querySelectorAll('[data-count]').forEach(b=>b.onclick=async()=>{try{let x=await api('/notices/'+b.dataset.count+'/read-count');$('#count-'+b.dataset.count).textContent=x.count+' phụ huynh đã xác nhận'}catch(err){error(err)}});
}

async function adminView(){
 if(user.role!=='admin')return;
 const users=await api('/admin/users'),allClasses=await api('/classes');
 $('#app').innerHTML=`<div class="card"><div class="row"><h2>⚙️ Quản trị Smart Class</h2><div><button class="secondary" id="back">Về trang lớp</button> <button class="secondary" id="logout">Đăng xuất</button></div></div><p class="muted">Chỉ nhập dữ liệu giả lập trong giai đoạn thử nghiệm.</p></div>
 <div class="card"><h2>1. Tạo tài khoản</h2><form id="newUser"><label>Tên đăng nhập<input name="username" required pattern="[a-zA-Z0-9_.-]{3,60}"></label><label>Họ tên<input name="name" required></label><label>Vai trò<select name="role"><option value="teacher">Giáo viên</option><option value="parent">Phụ huynh</option></select></label><label>Mật khẩu khởi tạo (ít nhất 12 ký tự)<input name="password" type="password" minlength="12" required></label><button>Tạo tài khoản</button></form></div>
 <div class="card"><h2>2. Tạo lớp</h2><form id="newClass"><label>Tên lớp<input name="name" placeholder="10A3" required></label><label>Năm học<input name="school_year" value="2026-2027" required></label><button>Tạo lớp</button></form></div>
 <div class="card"><h2>3. Phân công giáo viên</h2><form id="assign"><label>Giáo viên<select name="teacher_id">${users.filter(x=>x.role==='teacher').map(x=>`<option value="${x.id}">${esc(x.name)} (${esc(x.username)})</option>`).join('')}</select></label><label>Lớp<select name="class_id">${allClasses.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><button>Phân công</button></form></div>
 <div class="card"><h2>4. Nhập danh sách học sinh CSV</h2><p class="muted">Xuất Excel thành CSV UTF-8 với hai cột: code,name. Tối đa 500 dòng/lần. Nếu trùng mã, toàn bộ lần nhập bị hủy.</p><form id="importStudents"><label>Lớp<select name="class_id">${allClasses.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><label>Tệp CSV UTF-8<input type="file" name="file" accept=".csv,text/csv" required></label><button>Nhập học sinh</button></form></div>
 <div class="card"><h2>6. Quản lý tài khoản</h2><form id="resetPassword"><label>Tài khoản giáo viên / phụ huynh<select name="user_id">${users.filter(x=>x.role!=='admin').map(x=>`<option value="${x.id}">${esc(x.name)} (${esc(x.username)})</option>`).join('')}</select></label><label>Mật khẩu mới (tối thiểu 12 ký tự)<input name="new_password" type="password" minlength="12" required></label><button>Đặt lại mật khẩu</button></form><form id="accountStatus"><label>Tài khoản<select name="user_id">${users.filter(x=>x.role!=='admin').map(x=>`<option value="${x.id}">${esc(x.name)} (${esc(x.username)}) — ${x.active?'Đang hoạt động':'Đã khóa'}</option>`).join('')}</select></label><label>Trạng thái<select name="active"><option value="false">Khóa tài khoản</option><option value="true">Mở tài khoản</option></select></label><button>Cập nhật trạng thái</button></form></div>
 <div class="card"><h2>5. Liên kết phụ huynh – học sinh</h2><form id="linkParent"><label>Phụ huynh<select name="parent_id">${users.filter(x=>x.role==='parent').map(x=>`<option value="${x.id}">${esc(x.name)} (${esc(x.username)})</option>`).join('')}</select></label><label>Chọn lớp<select id="linkClass">${allClasses.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><label>Học sinh<select name="student_id" id="linkStudent"></select></label><button>Liên kết</button></form></div><div class="card"><p id="adminMessage" role="status"></p></div>`;
 $('#back').onclick=()=>load().catch(error);
 $('#logout').onclick=async()=>{await api('/logout',{method:'POST'});user=null;loginView()};
 const msg=t=>{$('#adminMessage').textContent=t};
 const attach=(selector,path,transform)=>{$(selector).onsubmit=async e=>{e.preventDefault();try{const payload=await transform(e.target);const result=await api(path,{method:'POST',body:JSON.stringify(payload)});msg('Thao tác thành công'+(result.imported?' — Đã nhập '+result.imported+' học sinh':''));if(selector!=='#linkParent')setTimeout(()=>adminView().catch(error),800)}catch(err){msg('Lỗi: '+err.message)}}};
 const fields=form=>Object.fromEntries(new FormData(form));
 attach('#newUser','/admin/users',async form=>fields(form));
 attach('#newClass','/admin/classes',async form=>fields(form));
 attach('#assign','/admin/assign-teacher',async form=>{let d=fields(form);return {teacher_id:Number(d.teacher_id),class_id:Number(d.class_id)}});
 attach('#importStudents','/admin/import-students',async form=>{let d=fields(form);if(d.file.size>300000)throw Error('Tệp quá lớn');return {class_id:Number(d.class_id),csv_text:await d.file.text()}});
 attach('#resetPassword','/admin/reset-password',async form=>{let d=fields(form);return {user_id:Number(d.user_id),new_password:d.new_password}});
 attach('#accountStatus','/admin/account-status',async form=>{let d=fields(form);return {user_id:Number(d.user_id),active:d.active==='true'}});
 attach('#linkParent','/admin/link-parent',async form=>{let d=fields(form);return {parent_id:Number(d.parent_id),student_id:Number(d.student_id)}});
 const loadStudents=async()=>{const students=await api('/students?class_id='+$('#linkClass').value);$('#linkStudent').innerHTML=students.map(x=>`<option value="${x.id}">${esc(x.code)} — ${esc(x.name)}</option>`).join('')};
 $('#linkClass').onchange=()=>loadStudents().catch(error);await loadStudents();
}

api('/me').then(u=>{user=u;return load()}).catch(()=>loginView());
