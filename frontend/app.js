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
function vnTime(value){
 if(!value)return '—';
 const iso=String(value).replace(' ','T');
 const normalized=/[zZ]|[+-]\d\d:?\d\d$/.test(iso)?iso:iso+'Z';
 const d=new Date(normalized);
 return Number.isNaN(d.getTime())?String(value):new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(d);
}
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
  ${user.role==='parent'?`<div class="card"><h2>🔔 Thông báo điện thoại</h2><p class="muted">Cài Smart Class vào màn hình chính và cho phép thông báo để nhận tin mới.</p><button id="enablePush">Bật thông báo</button> <button id="disablePush" class="secondary">Tắt thông báo</button><p id="pushStatus" class="muted"></p></div>`:''}
  <div class="card"><h2>Học sinh ${user.role==='parent'?'của gia đình':'trong lớp'}</h2>${students.length?`<table><thead><tr><th>Mã</th><th>Họ tên</th></tr></thead><tbody>${students.map(s=>`<tr><td>${esc(s.code)}</td><td>${esc(s.name)}</td></tr>`).join('')}</tbody></table>`:'Chưa có dữ liệu'}</div>
  ${user.role==='parent'?'':`<div class="card"><h2>Đăng thông báo cho lớp</h2><form id="noticeForm"><label>Tiêu đề<input name="title" maxlength="120" required></label><label>Nội dung<textarea name="body" maxlength="3000" required></textarea></label><label>Người nhận<select name="audience" id="noticeAudience"><option value="class">Toàn bộ phụ huynh trong lớp</option><option value="selected">Riêng phụ huynh của học sinh được chọn</option></select></label><div id="studentTargetBox" hidden><label>Chọn học sinh (giữ Ctrl trên máy tính để chọn nhiều)<select id="noticeTargets" multiple size="5">${students.map(s=>`<option value="${s.id}">${esc(s.code)} — ${esc(s.name)}</option>`).join('')}</select></label><p class="muted">Chỉ phụ huynh liên kết với học sinh được chọn mới xem được nội dung.</p></div><label>Đính kèm (tối đa 5 tệp JPG/PNG/PDF/DOCX, mỗi tệp ≤8 MB)<input type="file" name="files" multiple accept=".jpg,.jpeg,.png,.pdf,.docx"></label><button>Đăng thông báo</button></form><p id="error" class="error"></p></div>`}
  ${user.role==='parent'?`<div class="card"><h2>💬 Phản hồi</h2><p class="muted">Chọn thông báo cần trao đổi. Nội dung chỉ hiển thị cho gia đình và giáo viên phụ trách.</p>${notices.length?notices.map(n=>`<div class="row mini-record"><span>${esc(n.title)}</span><button class="secondary" data-open-parent-reply="${n.id}">Viết / Xem phản hồi</button></div><div id="parent-thread-${n.id}"></div>`).join(''):'Chưa có thông báo để phản hồi.'}</div>`:''}
  ${user.role==='parent'?`<div class="card"><h2>📝 Đơn xin nghỉ học</h2><form id="absenceForm"><label>Học sinh<select name="student_id" required>${students.map(x=>`<option value="${x.id}">${esc(x.name)} (${esc(x.code)})</option>`).join('')}</select></label><label>Ngày xin nghỉ<input type="date" name="absence_date" required></label><label>Buổi học<select name="session"><option value="morning">Sáng</option><option value="afternoon">Chiều</option><option value="full">Cả ngày</option></select></label><label>Lý do<textarea name="reason" maxlength="1000" required placeholder="Nhập lý do xin nghỉ"></textarea></label><label class="row"><input type="checkbox" name="confirmed" required style="width:auto;margin:0"> Tôi xác nhận thông tin trên là đúng</label><button type="submit">Gửi đơn xin nghỉ</button></form><p class="muted">Đơn chỉ có hiệu lực sau khi giáo viên xử lý theo quy định nhà trường.</p></div>`:`<div class="card"><h2>📥 Hộp thư phụ huynh</h2><p class="muted">Các phản hồi được gửi riêng, không hiển thị cho phụ huynh khác.</p><div id="replyInbox">Đang tải...</div></div><div class="card"><h2>📋 Duyệt đơn nghỉ học</h2><div id="absenceInbox">Đang tải...</div></div>`}
  ${user.role==='parent'?`<div class="card"><h2>📋 Đơn xin nghỉ đã gửi</h2><div id="absenceInbox">Đang tải...</div></div>`:''}
  <div class="card"><h2>Thông báo lớp</h2>${notices.length?notices.map(n=>`<article style="padding:14px 0;border-bottom:1px solid #eee"><div class="row"><strong>${esc(n.title)}</strong><span class="tag">${esc(vnTime(n.created_at))}</span></div>${n.audience==='selected'?`<p class="muted">🔒 Thông báo riêng: ${esc(n.target_names||'Phụ huynh được chọn')}</p>`:''}<p class="notice">${esc(n.body)}</p><small class="muted">Người đăng: ${esc(n.author)}</small><div id="attachments-${n.id}" class="attachments"></div>${user.role==='parent'?`<div style="margin-top:10px"><button data-read="${n.id}" ${n.is_read?'disabled':''}>${n.is_read?'✓ Đã đọc':'Xác nhận đã đọc'}</button> <button class="secondary" data-replies="${n.id}">💬 Phản hồi</button><div id="reply-thread-${n.id}"></div></div>`:`<div style="margin-top:8px"><button class="secondary" data-count="${n.id}">Ai đã đọc / chưa đọc?</button> <button class="secondary" data-delete-notice="${n.id}">Xóa thông báo</button> <div id="count-${n.id}"></div><label>Thêm tệp cho thông báo này<input type="file" data-attach="${n.id}" accept=".jpg,.jpeg,.png,.pdf,.docx"></label></div>`}</article>`).join(''):'Chưa có thông báo'}</div>`;
  if(user.role==='parent'){
    const form=$('#absenceForm');if(form){form.querySelector('[name="absence_date"]').value=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    form.onsubmit=async e=>{e.preventDefault();const f=new FormData(form);try{await api('/absence-requests',{method:'POST',body:JSON.stringify({student_id:Number(f.get('student_id')),absence_date:f.get('absence_date'),session:f.get('session'),reason:f.get('reason')})});alert('Đã gửi đơn. Vui lòng chờ giáo viên xử lý.');await load()}catch(err){error(err)}};}
  }
  await renderAbsence();
  if(user.role!=='parent')await renderReplyInbox();
  document.querySelectorAll('[data-replies]').forEach(b=>b.onclick=()=>showReplyThread(Number(b.dataset.replies),null,'#reply-thread-'+b.dataset.replies).catch(error));
  document.querySelectorAll('[data-open-parent-reply]').forEach(b=>b.onclick=()=>showReplyThread(Number(b.dataset.openParentReply),null,'#parent-thread-'+b.dataset.openParentReply).catch(error));
  if(user.role==='admin'){const nav=document.createElement('div');nav.className='card';nav.innerHTML='<button id="adminPanel">⚙️ Quản trị lớp và tài khoản</button>';$('#app').prepend(nav);$('#adminPanel').onclick=()=>adminView().catch(error)}
  setupPasswordToggles();
  if(user.role==='parent'){ $('#enablePush').onclick=()=>enablePush().catch(error);$('#disablePush').onclick=()=>disablePush().catch(error) }
  $('#changePassword').onsubmit=async e=>{e.preventDefault();try{await api('/account/change-password',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});alert('Đã đổi mật khẩu. Vui lòng đăng nhập lại.');user=null;loginView()}catch(err){error(err)}};
  $('#class').onchange=e=>{selected=Number(e.target.value);load().catch(error)};
  $('#logout').onclick=async()=>{await api('/logout',{method:'POST'});user=null;loginView()};
  if($('#noticeAudience'))$('#noticeAudience').onchange=e=>{$('#studentTargetBox').hidden=e.target.value!=='selected'};
  document.querySelectorAll('[data-delete-notice]').forEach(b=>b.onclick=async()=>{if(!confirm('Ẩn thông báo này khỏi tất cả phụ huynh? Thao tác sẽ được ghi nhật ký.'))return;try{await api('/notices/'+b.dataset.deleteNotice,{method:'DELETE'});await load()}catch(e){error(e)}});
  if($('#noticeForm'))$('#noticeForm').onsubmit=async e=>{e.preventDefault();let f=new FormData(e.target);try{
   let files=[...e.target.querySelector('input[name="files"]').files];
   if(files.length>5||files.some(x=>x.size>8*1024*1024))throw Error('Tối đa 5 tệp, mỗi tệp 8 MB');
   const student_ids=f.get('audience')==='selected'?[...$('#noticeTargets').selectedOptions].map(o=>Number(o.value)):[];
   if(f.get('audience')==='selected'&&!student_ids.length)throw Error('Hãy chọn ít nhất một học sinh');
   let result=await api('/notices',{method:'POST',body:JSON.stringify({class_id:selected,title:f.get('title'),body:f.get('body'),student_ids})});
   let failed=[];for(const file of files){try{await uploadFile(result.id,file)}catch(err){failed.push(file.name+': '+err.message)}}
   await load();if(failed.length)alert('Đã đăng thông báo nhưng có tệp tải lên thất bại: '+failed.join('; '));
 }catch(err){error(err)}};
  document.querySelectorAll('[data-read]').forEach(b=>b.onclick=async()=>{try{await api('/notices/'+b.dataset.read+'/read',{method:'POST'});await load()}catch(err){error(err)}});
  document.querySelectorAll('[data-count]').forEach(b=>b.onclick=async()=>{try{let x=await api('/notices/'+b.dataset.count+'/read-status');$('#count-'+b.dataset.count).innerHTML=`<p><b>Đã đọc ${x.read}/${x.total}</b> phụ huynh</p><button class="secondary" data-remind-all="${b.dataset.count}">🔔 Nhắc tất cả người chưa đọc</button><table><thead><tr><th>Phụ huynh</th><th>Học sinh hiện liên kết</th><th>Trạng thái</th></tr></thead><tbody>${x.parents.map(p=>`<tr><td>${esc(p.name)} (${esc(p.username)})</td><td>${esc(p.student_names||'—')}</td><td>${p.read_at?'✓ Đã đọc: '+esc(vnTime(p.read_at)):'Chưa đọc'}</td></tr>`).join('')}</tbody></table>`;const remind=$('[data-remind-all="'+b.dataset.count+'"]');if(remind)remind.onclick=async()=>{if(!confirm('Gửi nhắc nhở đến các phụ huynh chưa đọc? Tối đa một lần/24 giờ.'))return;try{const res=await api('/notices/'+b.dataset.count+'/remind',{method:'POST',body:JSON.stringify({})});alert('Đã gửi đến '+res.parents_notified+' phụ huynh có thiết bị đăng ký.')}catch(e){error(e)}}}catch(err){error(err)}});
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
 $('#app').innerHTML=`<div class="card"><div class="row"><h2>⚙️ Quản trị Smart Class</h2><div><button class="secondary" id="back">Về trang lớp</button> <button class="secondary" id="logout">Đăng xuất</button></div></div></div>
 <div class="card"><h2>1. Tạo tài khoản</h2><form id="newUser"><label>Tên đăng nhập<input name="username" required pattern="[a-zA-Z0-9_.-]{3,60}"></label><label>Họ tên<input name="name" required></label><label>Vai trò<select name="role"><option value="teacher">Giáo viên</option><option value="parent">Phụ huynh</option></select></label>${passwordField("password","Mật khẩu khởi tạo (ít nhất 12 ký tự)",'minlength="12" required')}<button>Tạo tài khoản</button></form></div>
 <div class="card"><h2>2. Tạo lớp</h2><form id="newClass"><label>Tên lớp<input name="name" placeholder="10A3" required></label><label>Năm học<input name="school_year" value="2026-2027" required></label><button>Tạo lớp</button></form></div>
 <div class="card"><h2>3. Phân công giáo viên</h2><form id="assign"><label>Giáo viên<select name="teacher_id">${users.filter(x=>x.role==='teacher').map(x=>`<option value="${x.id}">${esc(x.name)} (${esc(x.username)})</option>`).join('')}</select></label><label>Lớp<select name="class_id">${allClasses.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><button>Phân công</button></form></div>
 <div class="card"><h2>4. Nhập danh sách học sinh CSV</h2><p class="muted">Xuất Excel thành CSV UTF-8 với hai cột: code,name. Tối đa 500 dòng/lần. Nếu trùng mã, toàn bộ lần nhập bị hủy.</p><form id="importStudents"><label>Lớp<select name="class_id">${allClasses.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><label>Tệp CSV UTF-8<input type="file" name="file" accept=".csv,text/csv" required></label><button>Nhập học sinh</button></form></div>
 <div class="card"><h2>6. Quản lý tài khoản</h2><form id="resetPassword"><label>Tài khoản giáo viên / phụ huynh<select name="user_id">${users.filter(x=>x.role!=='admin').map(x=>`<option value="${x.id}">${esc(x.name)} (${esc(x.username)})</option>`).join('')}</select></label>${passwordField("new_password","Mật khẩu mới (tối thiểu 12 ký tự)",'minlength="12" required')}<button>Đặt lại mật khẩu</button></form><form id="accountStatus"><label>Tài khoản<select name="user_id">${users.filter(x=>x.role!=='admin').map(x=>`<option value="${x.id}">${esc(x.name)} (${esc(x.username)}) — ${x.active?'Đang hoạt động':'Đã khóa'}</option>`).join('')}</select></label><label>Trạng thái<select name="active"><option value="false">Khóa tài khoản</option><option value="true">Mở tài khoản</option></select></label><button>Cập nhật trạng thái</button></form></div>
 <div class="card"><h2>5. Liên kết phụ huynh – học sinh</h2><form id="linkParent"><label>Phụ huynh<select name="parent_id">${users.filter(x=>x.role==='parent').map(x=>`<option value="${x.id}">${esc(x.name)} (${esc(x.username)})</option>`).join('')}</select></label><label>Chọn lớp<select id="linkClass">${allClasses.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><label>Học sinh<select name="student_id" id="linkStudent"></select></label><button>Liên kết</button></form></div><div class="card"><h2>7. Quản lý học sinh (xóa mềm / khôi phục)</h2><label>Chọn lớp<select id="manageClass">${allClasses.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><div id="manageStudents"></div></div>
 <div class="card"><h2>9. Xóa vĩnh viễn tài khoản</h2><p class="muted">Chỉ xóa được tài khoản không còn liên kết hoặc lịch sử cần giữ. Hệ thống sẽ từ chối thao tác nguy hiểm.</p><div id="purgeUsers">${users.filter(x=>x.role!=='admin').map(x=>`<div style="margin:6px 0">${esc(x.name)} (${esc(x.username)}) <button class="secondary" data-purge-user="${x.id}" data-username="${esc(x.username)}">Xóa vĩnh viễn</button></div>`).join('')}</div></div><div class="card"><h2>8. Danh sách liên kết phụ huynh – học sinh</h2><label>Lọc lớp<select id="linksClass"><option value="">Tất cả các lớp</option>${allClasses.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><div id="linksList"></div></div>
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
 const renderStudents=async()=>{const classId=$('#manageClass').value;if(!classId)return;const rows=await api('/admin/students?class_id='+classId);$('#manageStudents').innerHTML=`<table><thead><tr><th>Mã</th><th>Họ tên</th><th>Thao tác</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.code)}</td><td>${esc(r.name)}</td><td><button class="secondary" data-student="${r.id}" data-restore="${!!r.deleted_at}">${r.deleted_at?'Khôi phục':'Xóa mềm'}</button> <button class="secondary" data-purge-student="${r.id}" data-code="${esc(r.code)}">Xóa vĩnh viễn</button></td></tr>`).join('')}</tbody></table>`;document.querySelectorAll('[data-purge-student]').forEach(b=>b.onclick=async()=>{const code=prompt('Xóa không thể khôi phục. Nhập chính xác mã học sinh: '+b.dataset.code);if(code===null)return;try{await api('/admin/students/'+b.dataset.purgeStudent+'/purge',{method:'POST',body:JSON.stringify({confirm:code})});await renderStudents();msg('Đã xóa vĩnh viễn học sinh')}catch(e){msg('Lỗi: '+e.message)}});document.querySelectorAll('[data-student]').forEach(b=>b.onclick=async()=>{if(!confirm(b.dataset.restore==='true'?'Khôi phục học sinh?':'Lưu trữ học sinh? Học sinh sẽ ẩn khỏi danh sách hoạt động.'))return;try{const id=b.dataset.student,restore=b.dataset.restore==='true';await api('/admin/students/'+id+(restore?'/restore':''),{method:restore?'POST':'DELETE'});await renderStudents();msg('Đã cập nhật học sinh')}catch(err){msg('Lỗi: '+err.message)}})};
 const renderLinks=async()=>{const v=$('#linksClass').value;const rows=await api('/admin/parent-links'+(v?'?class_id='+v:''));$('#linksList').innerHTML=`<table><thead><tr><th>Lớp / Học sinh</th><th>Phụ huynh</th><th>Thao tác</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.class_name)} / ${esc(r.student_code)} - ${esc(r.student_name)}${r.student_archived?' (đã lưu trữ)':''}</td><td>${esc(r.parent_name)} (${esc(r.parent_username)})</td><td><button class="secondary" data-unlink="${r.parent_id}:${r.student_id}">Hủy liên kết</button></td></tr>`).join('')}</tbody></table>`;document.querySelectorAll('[data-unlink]').forEach(b=>b.onclick=async()=>{if(!confirm('Hủy liên kết phụ huynh và học sinh này?'))return;try{const [p,s]=b.dataset.unlink.split(':');await api('/admin/parent-links/'+p+'/'+s,{method:'DELETE'});await renderLinks();msg('Đã hủy liên kết')}catch(err){msg('Lỗi: '+err.message)}})};
 document.querySelectorAll('[data-purge-user]').forEach(b=>b.onclick=async()=>{const name=prompt('Xóa tài khoản không thể khôi phục. Nhập chính xác tên đăng nhập: '+b.dataset.username);if(name===null)return;try{await api('/admin/users/'+b.dataset.purgeUser+'/purge',{method:'POST',body:JSON.stringify({confirm:name})});await adminView()}catch(e){msg('Lỗi: '+e.message)}});
 $('#manageClass').onchange=()=>renderStudents().catch(error);$('#linksClass').onchange=()=>renderLinks().catch(error);
 if(allClasses.length)await renderStudents();await renderLinks();
}

api('/me').then(u=>{user=u;return load()}).catch(()=>loginView());

function base64ToBytes(value){const b64=value.replace(/-/g,'+').replace(/_/g,'/');const raw=atob(b64+'='.repeat((4-b64.length%4)%4));return Uint8Array.from(raw,c=>c.charCodeAt(0))}
async function enablePush(){
 if(!('serviceWorker' in navigator)||!('PushManager' in window)||!('Notification' in window))throw Error('Thiết bị/trình duyệt chưa hỗ trợ Web Push');
 const config=await api('/push/public-key');if(!config.enabled)throw Error('Máy chủ chưa cấu hình VAPID');
 const permission=await Notification.requestPermission();if(permission!=='granted')throw Error('Chưa cấp quyền thông báo');
 const registration=await navigator.serviceWorker.ready;
 let sub=await registration.pushManager.getSubscription();
 if(!sub)sub=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:base64ToBytes(config.public_key)});
 await api('/push/subscribe',{method:'POST',body:JSON.stringify(sub.toJSON())});
 $('#pushStatus').textContent='Đã bật thông báo trên thiết bị này';
}
async function disablePush(){
 const registration=await navigator.serviceWorker.ready;const sub=await registration.pushManager.getSubscription();
 if(sub){await api('/push/unsubscribe',{method:'POST',body:JSON.stringify(sub.toJSON())});await sub.unsubscribe()}
 $('#pushStatus').textContent='Đã tắt thông báo trên thiết bị này';
}

// Smart Class 4.4: secure feedback and leave request UI.
const absenceLabels={pending:'Chờ xử lý',approved:'Đã đồng ý',needs_info:'Cần bổ sung',rejected:'Không đồng ý'};
const sessionLabels={morning:'Sáng',afternoon:'Chiều',full:'Cả ngày'};
async function renderAbsence(){
 const box=$('#absenceInbox');if(!box)return;
 try{
  const rows=await api('/absence-requests?class_id='+selected);
  box.innerHTML=rows.length?rows.map(x=>`<article class="mini-record"><div class="row"><strong>${esc(x.student_name)}</strong><span class="tag">${esc(absenceLabels[x.status]||x.status)}</span></div><p>Ngày ${esc(x.absence_date)} · ${esc(sessionLabels[x.session])}<br><span class="muted">Phụ huynh: ${esc(x.parent_name)}</span></p><p class="notice">${esc(x.reason)}</p>${x.teacher_note?`<p><b>Ý kiến giáo viên:</b> ${esc(x.teacher_note)}</p>`:''}${user.role!=='parent'&&x.status==='pending'?`<div class="row"><button data-review="${x.id}" data-status="approved">Đồng ý</button><button class="secondary" data-review="${x.id}" data-status="needs_info">Cần bổ sung</button><button class="secondary" data-review="${x.id}" data-status="rejected">Không đồng ý</button></div>`:''}</article>`).join(''):'Chưa có đơn xin nghỉ học.';
  box.querySelectorAll('[data-review]').forEach(b=>b.onclick=async()=>{
   const status=b.dataset.status;
   const note=prompt('Ý kiến giáo viên (có thể để trống nếu đồng ý):','');if(note===null)return;
   if(status!=='approved'&&!note.trim()){alert('Vui lòng nhập lý do cần bổ sung hoặc không đồng ý.');return}
   try{await api('/absence-requests/'+b.dataset.review+'/review',{method:'POST',body:JSON.stringify({status,teacher_note:note})});await renderAbsence()}catch(e){error(e)}
  });
 }catch(e){box.textContent='Không tải được đơn: '+e.message}
}
async function renderReplyInbox(){
 const box=$('#replyInbox');if(!box)return;
 try{const rows=await api('/replies/inbox?class_id='+selected);
  box.innerHTML=rows.length?rows.map(x=>`<div class="mini-record"><div class="row"><div><strong>${esc(x.parent_name)}</strong><p class="muted">${esc(x.title)} · ${esc(vnTime(x.last_reply_at))}</p></div><button class="secondary" data-open-reply="${x.notice_id}" data-parent="${x.parent_id}">Xem / Trả lời</button></div><div id="inbox-thread-${x.notice_id}-${x.parent_id}"></div></div>`).join(''):'Chưa có phản hồi từ phụ huynh.';
  box.querySelectorAll('[data-open-reply]').forEach(b=>b.onclick=()=>showReplyThread(Number(b.dataset.openReply),Number(b.dataset.parent),'#inbox-thread-'+b.dataset.openReply+'-'+b.dataset.parent).catch(error));
 }catch(e){box.textContent='Không tải được hộp thư: '+e.message}
}
async function showReplyThread(noticeId,parentId,targetSelector){
 const box=$(targetSelector);if(!box)return;
 const q=parentId?'?parent_id='+parentId:'';
 const messages=await api('/notices/'+noticeId+'/replies'+q);
 box.innerHTML=`<div class="thread">${messages.length?messages.map(m=>`<p><b>${esc(m.sender_name)}</b> <small class="muted">${esc(vnTime(m.created_at))}</small><span class="notice">${esc(m.body)}</span></p>`).join(''):'<p class="muted">Chưa có phản hồi.</p>'}<form class="replyForm"><label>Nội dung phản hồi<textarea name="body" maxlength="2000" required></textarea></label><button>Gửi phản hồi</button></form></div>`;
 box.querySelector('form').onsubmit=async e=>{e.preventDefault();const body=new FormData(e.target).get('body');try{await api('/notices/'+noticeId+'/replies',{method:'POST',body:JSON.stringify({body,parent_id:parentId})});await showReplyThread(noticeId,parentId,targetSelector)}catch(err){error(err)}};
}
