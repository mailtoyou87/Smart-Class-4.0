let user=null,classes=[],selected=null;
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,opts={}){
  const r=await fetch('/api'+path,{credentials:'same-origin',...opts,headers:{'X-Smart-Request':'1','Content-Type':'application/json',...(opts.headers||{})}});
  if(!r.ok){let data=await r.json().catch(()=>({}));throw Error(data.detail||'Lỗi kết nối')}
  return r.json();
}
function passwordField(name,label,extra=''){
 return `<label>${label}<span class="password-wrap"><input name="${name}" type="password" ${extra}><button type="button" class="pw-toggle secondary" aria-label="Hiện mật khẩu" title="Hiện/ẩn mật khẩu">👁</button></span></label>`;
}
function setupPasswordToggles(){document.querySelectorAll('.pw-toggle').forEach(b=>b.onclick=()=>{const inp=b.parentElement.querySelector('input');inp.type=inp.type==='password'?'text':'password';b.textContent=inp.type==='password'?'👁':'🙈';b.setAttribute('aria-label',inp.type==='password'?'Hiện mật khẩu':'Ẩn mật khẩu')})}
const error=e=>{let el=$('#error');if(el)el.textContent=e.message;else alert(e.message)};
function loginView(){
  $('#app').innerHTML=`<div class="card"><h2>Đăng nhập</h2><form id="login"><label>Tài khoản<input name="username" autocomplete="username" required></label>${passwordField("password","Mật khẩu",'autocomplete="current-password" required')}<button>Đăng nhập</button></form><p id="error" class="error"></p></div>`;
  setupPasswordToggles();
  $('#login').onsubmit=async e=>{e.preventDefault();let f=new FormData(e.target);try{user=await api('/login',{method:'POST',body:JSON.stringify(Object.fromEntries(f))});await load()}catch(err){error(err)}};
}
async function load(){
  classes=await api('/classes');selected=classes.some(c=>c.id===selected)?selected:classes[0]?.id;
  if(!selected){if(user.role==='admin'){await adminView();return}$('#app').innerHTML='<div class="card">Tài khoản chưa được phân lớp.</div>';return}
  let [students,notices]=await Promise.all([api('/students?class_id='+selected),api('/notices?class_id='+selected)]);
  $('#app').innerHTML=`<div class="card"><div class="row"><div><strong>${esc(user.name)}</strong> <span class="tag">${esc(user.role)}</span></div><button class="secondary" id="logout">Đăng xuất</button></div><label>Chọn lớp<select id="class">${classes.map(c=>`<option value="${c.id}" ${c.id===selected?'selected':''}>${esc(c.name)} (${esc(c.school_year)})</option>`).join('')}</select></label></div>
  <div class="card"><details><summary>Đổi mật khẩu</summary><form id="changePassword">${passwordField("current_password","Mật khẩu hiện tại","required")}${passwordField("new_password","Mật khẩu mới (tối thiểu 12 ký tự)",'minlength="12" required')}<button>Đổi mật khẩu</button></form></details></div>
  <div class="card"><h2>Học sinh ${user.role==='parent'?'của gia đình':'trong lớp'}</h2>${students.length?`<table><thead><tr><th>Mã</th><th>Họ tên</th></tr></thead><tbody>${students.map(s=>`<tr><td>${esc(s.code)}</td><td>${esc(s.name)}</td></tr>`).join('')}</tbody></table>`:'Chưa có dữ liệu'}</div>
  ${user.role==='parent'?'':`<div class="card"><h2>Đăng thông báo cho lớp</h2><form id="noticeForm"><label>Tiêu đề<input name="title" maxlength="120" required></label><label>Nội dung<textarea name="body" maxlength="3000" required></textarea></label><label>Đính kèm (tối đa 5 tệp JPG/PNG/PDF/DOCX, mỗi tệp ≤8 MB)<input type="file" name="files" multiple accept=".jpg,.jpeg,.png,.pdf,.docx"></label><button>Đăng thông báo</button></form><p id="error" class="error"></p></div>`}
  <div class="card"><h2>Thông báo lớp</h2>${notices.length?notices.map(n=>`<article style="padding:14px 0;border-bottom:1px solid #eee"><div class="row"><strong>${esc(n.title)}</strong><span class="tag">${esc(n.created_at)}</span></div><p class="notice">${esc(n.body)}</p><small class="muted">Người đăng: ${esc(n.author)}</small><div id="attachments-${n.id}" class="attachments"></div>${user.role==='parent'?`<div style="margin-top:10px"><button data-read="${n.id}" ${n.is_read?'disabled':''}>${n.is_read?'✓ Đã đọc':'Xác nhận đã đọc'}</button></div>`:`<div style="margin-top:8px"><button class="secondary" data-count="${n.id}">Ai đã đọc / chưa đọc?</button> <div id="count-${n.id}"></div><label>Thêm tệp cho thông báo này<input type="file" data-attach="${n.id}" accept=".jpg,.jpeg,.png,.pdf,.docx"></label></div>`}</article>`).join(''):'Chưa có thông báo'}</div>`;
  if(user.role==='admin'){const nav=document.createElement('div');nav.className='card';nav.innerHTML='<button id="adminPanel">⚙️ Quản trị lớp và tài khoản</button>';$('#app').prepend(nav);$('#adminPanel').onclick=()=>adminView().catch(error)}
  setupPasswordToggles();
  $('#changePassword').onsubmit=async e=>{e.preventDefault();try{await api('/account/change-password',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});alert('Đã đổi mật khẩu. Vui lòng đăng nhập lại.');user=null;loginView()}catch(err){error(err)}};
  $('#class').onchange=e=>{selected=Number(e.target.value);load().catch(error)};
  $('#logout').onclick=async()=>{await api('/logout',{method:'POST'});user=null;loginView()};
  if($('#noticeForm'))$('#noticeForm').onsubmit=async e=>{e.preventDefault();let f=new FormData(e.target);try{
   let files=[...e.target.querySelector('input[name="files"]').files];
   if(files.length>5||files.some(x=>x.size>8*1024*1024))throw Error('Tối đa 5 tệp, mỗi tệp 8 MB');
   let result=await api('/notices',{method:'POST',body:JSON.stringify({class_id:selected,title:f.get('title'),body:f.get('body')})});
   let failed=[];for(const file of files){try{await uploadFile(result.id,file)}catch(err){failed.push(file.name+': '+err.message)}}
   await load();if(failed.length)alert('Đã đăng thông báo nhưng có tệp tải lên thất bại: '+failed.join('; '));
 }catch(err){error(err)}};
  document.querySelectorAll('[data-read]').forEach(b=>b.onclick=async()=>{try{await api('/notices/'+b.dataset.read+'/read',{method:'POST'});await load()}catch(err){error(err)}});
  document.querySelectorAll('[data-count]').forEach(b=>b.onclick=async()=>{try{let x=await api('/notices/'+b.dataset.count+'/read-status');$('#count-'+b.dataset.count).innerHTML=`<p><b>Đã đọc ${x.read}/${x.total}</b> phụ huynh</p><table><thead><tr><th>Phụ huynh</th><th>Học sinh hiện liên kết</th><th>Trạng thái</th></tr></thead><tbody>${x.parents.map(p=>`<tr><td>${esc(p.name)} (${esc(p.username)})</td><td>${esc(p.student_names||'—')}</td><td>${p.read_at?'✓ Đã đọc: '+esc(p.read_at):'Chưa đọc'}</td></tr>`).join('')}</tbody></table>`}catch(err){error(err)}});
  document.querySelectorAll('[data-attach]').forEach(el=>el.onchange=async()=>{if(!el.files.length)return;try{await uploadFile(Number(el.dataset.attach),el.files[0]);await load()}catch(err){error(err)}});
  for(const n of notices){try{const a=await api('/notices/'+n.id+'/attachments');const target=$('#attachments-'+n.id);if(target)target.innerHTML=a.map(x=>`<div>📎 <a href="/api/attachments/${x.id}/download">${esc(x.filename)}</a> (${Math.round(x.file_size/1024)} KB) ${user.role!=='parent'?`<button type="button" class="secondary" data-delattach="${x.id}">Xóa tệp</button>`:''}</div>`).join('')}catch(e){console.warn(e)}}
  document.querySelectorAll('[data-delattach]').forEach(b=>b.onclick=async()=>{if(!confirm('Xóa tệp đính kèm này?'))return;try{await api('/attachments/'+b.dataset.delattach,{method:'DELETE'});await load()}catch(err){error(err)}});
}

async function uploadFile(noticeId,file){
 if(file.size>8*1024*1024)throw Error('Tệp vượt quá 8 MB');
 const form=new FormData();form.append('file',file);
 const r=await fetch('/api/notices/'+noticeId+'/attachments',{method:'POST',credentials:'same-origin',headers:{'X-Smart-Request':'1'},body:form});
 if(!r.ok){const e=await r.json().catch(()=>({}));throw Error(e.detail||'Tải tệp thất bại')}
 return r.json();
}
async function adminView(){
 if(user.role!=='admin')return;
 const users=await api('/admin/users'),allClasses=await api('/classes');
 $('#app').innerHTML=`<div class="card"><div class="row"><h2>⚙️ Quản trị Smart Class</h2><div><button class="secondary" id="back">Về trang lớp</button> <button class="secondary" id="logout">Đăng xuất</button></div></div><p class="muted">Chỉ nhập dữ liệu giả lập trong giai đoạn thử nghiệm.</p></div>
 <div class="card"><h2>1. Tạo tài khoản</h2><form id="newUser"><label>Tên đăng nhập<input name="username" required pattern="[a-zA-Z0-9_.-]{3,60}"></label><label>Họ tên<input name="name" required></label><label>Vai trò<select name="role"><option value="teacher">Giáo viên</option><option value="parent">Phụ huynh</option></select></label>${passwordField("password","Mật khẩu khởi tạo (ít nhất 12 ký tự)",'minlength="12" required')}<button>Tạo tài khoản</button></form></div>
 <div class="card"><h2>2. Tạo lớp</h2><form id="newClass"><label>Tên lớp<input name="name" placeholder="10A3" required></label><label>Năm học<input name="school_year" value="2026-2027" required></label><button>Tạo lớp</button></form></div>
 <div class="card"><h2>3. Phân công giáo viên</h2><form id="assign"><label>Giáo viên<select name="teacher_id">${users.filter(x=>x.role==='teacher').map(x=>`<option value="${x.id}">${esc(x.name)} (${esc(x.username)})</option>`).join('')}</select></label><label>Lớp<select name="class_id">${allClasses.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><button>Phân công</button></form></div>
 <div class="card"><h2>4. Nhập danh sách học sinh CSV</h2><p class="muted">Xuất Excel thành CSV UTF-8 với hai cột: code,name. Tối đa 500 dòng/lần. Nếu trùng mã, toàn bộ lần nhập bị hủy.</p><form id="importStudents"><label>Lớp<select name="class_id">${allClasses.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><label>Tệp CSV UTF-8<input type="file" name="file" accept=".csv,text/csv" required></label><button>Nhập học sinh</button></form></div>
 <div class="card"><h2>6. Quản lý tài khoản</h2><form id="resetPassword"><label>Tài khoản giáo viên / phụ huynh<select name="user_id">${users.filter(x=>x.role!=='admin').map(x=>`<option value="${x.id}">${esc(x.name)} (${esc(x.username)})</option>`).join('')}</select></label>${passwordField("new_password","Mật khẩu mới (tối thiểu 12 ký tự)",'minlength="12" required')}<button>Đặt lại mật khẩu</button></form><form id="accountStatus"><label>Tài khoản<select name="user_id">${users.filter(x=>x.role!=='admin').map(x=>`<option value="${x.id}">${esc(x.name)} (${esc(x.username)}) — ${x.active?'Đang hoạt động':'Đã khóa'}</option>`).join('')}</select></label><label>Trạng thái<select name="active"><option value="false">Khóa tài khoản</option><option value="true">Mở tài khoản</option></select></label><button>Cập nhật trạng thái</button></form></div>
 <div class="card"><h2>5. Liên kết phụ huynh – học sinh</h2><form id="linkParent"><label>Phụ huynh<select name="parent_id">${users.filter(x=>x.role==='parent').map(x=>`<option value="${x.id}">${esc(x.name)} (${esc(x.username)})</option>`).join('')}</select></label><label>Chọn lớp<select id="linkClass">${allClasses.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><label>Học sinh<select name="student_id" id="linkStudent"></select></label><button>Liên kết</button></form></div><div class="card"><h2>7. Quản lý học sinh (xóa mềm / khôi phục)</h2><label>Chọn lớp<select id="manageClass">${allClasses.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><div id="manageStudents"></div></div>
 <div class="card"><h2>8. Danh sách liên kết phụ huynh – học sinh</h2><label>Lọc lớp<select id="linksClass"><option value="">Tất cả các lớp</option>${allClasses.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><div id="linksList"></div></div>
 <div class="card"><p id="adminMessage" role="status"></p></div>`;
 setupPasswordToggles();
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
 $('#linkClass').onchange=()=>loadStudents().catch(error);if(allClasses.length)await loadStudents();
 const renderStudents=async()=>{const classId=$('#manageClass').value;if(!classId)return;const rows=await api('/admin/students?class_id='+classId);$('#manageStudents').innerHTML=`<table><thead><tr><th>Mã</th><th>Họ tên</th><th>Thao tác</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.code)}</td><td>${esc(r.name)}</td><td><button class="secondary" data-student="${r.id}" data-restore="${!!r.deleted_at}">${r.deleted_at?'Khôi phục':'Xóa mềm'}</button></td></tr>`).join('')}</tbody></table>`;document.querySelectorAll('[data-student]').forEach(b=>b.onclick=async()=>{if(!confirm(b.dataset.restore==='true'?'Khôi phục học sinh?':'Lưu trữ học sinh? Học sinh sẽ ẩn khỏi danh sách hoạt động.'))return;try{const id=b.dataset.student,restore=b.dataset.restore==='true';await api('/admin/students/'+id+(restore?'/restore':''),{method:restore?'POST':'DELETE'});await renderStudents();msg('Đã cập nhật học sinh')}catch(err){msg('Lỗi: '+err.message)}})};
 const renderLinks=async()=>{const v=$('#linksClass').value;const rows=await api('/admin/parent-links'+(v?'?class_id='+v:''));$('#linksList').innerHTML=`<table><thead><tr><th>Lớp / Học sinh</th><th>Phụ huynh</th><th>Thao tác</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.class_name)} / ${esc(r.student_code)} - ${esc(r.student_name)}${r.student_archived?' (đã lưu trữ)':''}</td><td>${esc(r.parent_name)} (${esc(r.parent_username)})</td><td><button class="secondary" data-unlink="${r.parent_id}:${r.student_id}">Hủy liên kết</button></td></tr>`).join('')}</tbody></table>`;document.querySelectorAll('[data-unlink]').forEach(b=>b.onclick=async()=>{if(!confirm('Hủy liên kết phụ huynh và học sinh này?'))return;try{const [p,s]=b.dataset.unlink.split(':');await api('/admin/parent-links/'+p+'/'+s,{method:'DELETE'});await renderLinks();msg('Đã hủy liên kết')}catch(err){msg('Lỗi: '+err.message)}})};
 $('#manageClass').onchange=()=>renderStudents().catch(error);$('#linksClass').onchange=()=>renderLinks().catch(error);
 if(allClasses.length)await renderStudents();await renderLinks();
}

api('/me').then(u=>{user=u;return load()}).catch(()=>loginView());
