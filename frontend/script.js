axios.defaults.baseURL = 'http://127.0.0.1:5000';

let token = '';
let isAdmin = false;
const ACADEMIC_WEEK_OFFSET = 6;

// Палитра цветов
const EVENT_COLORS = ['#36f', '#69f', '#39f'];

// Контрастный цвет текста (черный/белый) по формуле YIQ
function getContrastYIQ(hexcolor) {
  hexcolor = hexcolor.replace('#','');
  const r = parseInt(hexcolor.substr(0,2),16);
  const g = parseInt(hexcolor.substr(2,2),16);
  const b = parseInt(hexcolor.substr(4,2),16);
  const yiq = ((r*299)+(g*587)+(b*114))/1000;
  return yiq >= 128 ? '#000' : '#fff';
}

// Вычислить ISO-неделю для даты
function getISOWeek(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = (d.getUTCDay()+6)%7; // Пн=0
  d.setUTCDate(d.getUTCDate()-dayNum+3);
  const firstThursday = d.valueOf();
  d.setUTCMonth(0,1);
  if(d.getUTCDay()!==4) {
    d.setUTCMonth(0,1+((4-d.getUTCDay())+7)%7);
  }
  return 1 + Math.round((firstThursday - d)/604800000);
}

// Дата начала ISO-недели w в году y
function getDateOfISOWeek(w,y) {
  const simple = new Date(y,0,1+(w-1)*7);
  const dow = simple.getDay()||7;
  if(dow<=4) simple.setDate(simple.getDate()-dow+1);
  else simple.setDate(simple.getDate()+8-dow);
  return simple;
}

$(function(){
  // 1) автокомплит групп
  axios.get('/groups').then(res=>{
    $('#addGroup,#editGroup').autocomplete({ source: res.data });
  });

  // 2) datepicker
  $('#addDate,#editDate').datepicker({ dateFormat:'dd.mm.yy', regional:'ru' });

  // 3) селектор недель
  const year = new Date().getFullYear();
  for(let w=1; w<=19; w++){
    const isoW = w + ACADEMIC_WEEK_OFFSET;
    const start = getDateOfISOWeek(isoW, year);
    const end   = new Date(start); end.setDate(start.getDate()+6);
    const fmt = d=> String(d.getDate()).padStart(2,'0')+'.'
                + String(d.getMonth()+1).padStart(2,'0');
    $('#roomWeekInput').append(
      `<option value="${w}">${w} (${fmt(start)} – ${fmt(end)})</option>`
    );
  }

  // 4) загрузить список кабинетов
  axios.get('/allowed_rooms')
    .then(res=> res.data.forEach(r=>
      $('#roomSelect').append(`<option>${r}</option>`)
    ))
    .catch(()=> alert('Не удалось загрузить список кабинетов'));

  // 5) включать “Показать” когда выбрано всё
  $('#roomSelect,#roomWeekInput').on('change', ()=>{
    const ok = $('#roomSelect').val() && $('#roomWeekInput').val();
    $('#loadRoomsBtn').prop('disabled', !ok);
  });

  // 6) регистрация
  $('#registerBtn').click(async()=>{
    try {
      await axios.post('/register', {
        email: $('#regEmail').val(),
        password: $('#regPassword').val()
      });
      alert('Вы зарегистрированы, выполните вход.');
      $('#registerModal').modal('hide');
    } catch(e){
      alert('Ошибка регистрации: ' + (e.response?.data?.msg || e));
    }
  });

  // 7) вход
  $('#loginBtn').click(async()=>{
    try {
      const res = await axios.post('/login', {
        email: $('#email').val(),
        password: $('#password').val()
      });
      token = res.data.access_token;
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      $('#loginModal').modal('hide');
      $('#loginLink,#registerLink').addClass('d-none');
      $('#logoutLink').removeClass('d-none');
      isAdmin = !!res.data.is_admin;
      if(isAdmin) $('#addBtn,#manageUsersNav').removeClass('d-none');
    } catch(e){
      alert('Ошибка входа: ' + (e.response?.data?.msg || e));
    }
  });

  // 8) выход
  $('#logoutLink').click(()=>{
    token = ''; delete axios.defaults.headers.common['Authorization'];
    isAdmin = false;
    $('#addBtn,#manageUsersNav').addClass('d-none');
    $('#logoutLink').addClass('d-none');
    $('#loginLink,#registerLink').removeClass('d-none');
  });

  // 9) открыть модал “Добавить пару”
  $('#addBtn').click(()=> $('#addModal').modal('show'));

  // 10) добавить пару
  $('#addPairBtn').click(async()=>{
    const group = $('#addGroup').val().trim();
    const subj  = $('#addSubject').val().trim();
    const teach = $('#addTeacher').val().trim();
    const raw   = $('#addDate').val().trim();
    const st    = $('#addStartTime').val();
    const et    = $('#addEndTime').val();
    const room  = $('#roomSelect').val();
    if(!group||!subj||!teach||!raw||!st||!et){
      return alert('Заполните все поля формы.');
    }
    // формат даты: "Чт, 22 мая"
    const [dd,mm,yy] = raw.split('.').map(Number);
    const D = new Date(yy, mm-1, dd);
    const wkNames = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб'];
    const moNames = ['','января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];
    const dayFmt = `${wkNames[D.getDay()]}, ${dd} ${moNames[mm]}`;
    const acadW  = getISOWeek(D) - ACADEMIC_WEEK_OFFSET;

    const entry = {
      group_name: group,
      date:       dayFmt,
      time:       `${st} - ${et}`,
      subject:    subj,
      teachers:   [teach],
      rooms:      [room],
      week:       acadW
    };

    // проверка дубля
    try {
      const chk = await axios.get('/schedule', {
        params: { group: group, week: acadW }
      });
      if(chk.data.some(it=>
        it.date===entry.date &&
        it.time===entry.time &&
        it.rooms.includes(room)
      )){
        return alert('Такая пара уже есть на этой неделе!');
      }
    } catch {
      return alert('Не удалось проверить дубли.');
    }

    // отправка
    try {
      await axios.post('/schedule', entry);
      $('#addModal').modal('hide');
      loadRooms();      // <-- теперь подтянет свежие данные
    } catch(e){
      alert('Ошибка добавления: ' + (e.response?.data?.msg || e));
    }
  });

  // 11) кнопка “Показать”
  $('#loadRoomsBtn').click(loadRooms);

  // 12) Управление пользователями: по клику на пункт меню грузим юзеров и открываем модалку
  $('#manageUsersNav').click(async () => {
    await loadUsers();        // подгрузили строки в таблицу
    $('#usersModal').modal('show'); // показали модалку
});
});
// ——— Загрузка / отрисовка расписания ———

async function loadRooms(){
  const room = $('#roomSelect').val();
  const week = $('#roomWeekInput').val();
  if (!room || !week) {
    return alert('Укажите кабинет и неделю.');
  }
  try {
    const res = await axios.get('/occupied_rooms', {
      params: { _: Date.now() }      // cache-buster
    });
    const data = res.data
      .filter(it => String(it.week)===week && it.room===room)
      .sort((a,b)=>{
        const order = { 'Пн':0,'Вт':1,'Ср':2,'Чт':3,'Пт':4,'Сб':5,'Вс':6 };
        const da = order[a.day.split(',')[0]],
              db = order[b.day.split(',')[0]];
        if (da!==db) return da-db;
        const [h1,m1]=a.start_time.split(':').map(Number),
              [h2,m2]=b.start_time.split(':').map(Number);
        return (h1*60+m1) - (h2*60+m2);
      });

    $('#calendar')
      .empty()
      .removeClass('d-none')
      .data('rawItems', data);

    renderCalendar(data);

  } catch(e) {
    console.error(e);
    alert('Не удалось загрузить расписание кабинета.');
  }
}

/* перерисовка расписания */
function renderCalendar(items) {
  // группируем по дню (поле day, а не date!)
  const byDate = items.reduce((acc, e) => {
    (acc[e.day] = acc[e.day] || []).push(e);
    return acc;
  }, {});

  const order = { 'Пн': 0, 'Вт': 1, 'Ср': 2, 'Чт': 3, 'Пт': 4, 'Сб': 5, 'Вс': 6 };

  $('#calendar').empty();               // очищаем грид

  Object.entries(byDate)
    .sort(([d1], [d2]) => order[d1.split(',')[0]] - order[d2.split(',')[0]])
    .forEach(([date, evs]) => {
      const col = $('<div>').addClass('day-column');
      $('<div>').addClass('day-header').text(date).appendTo(col);

      const wrap = $('<div>').addClass('events');

      evs.forEach((e, i) => {
        const bg = EVENT_COLORS[i % EVENT_COLORS.length];
        const fg = getContrastYIQ(bg);

        const card = $('<div>')
          .addClass('event-card')
          .css({ backgroundColor: bg, color: fg })
          .append(`<strong>${e.start_time} – ${e.end_time}</strong>`)
          .append(`<span>${e.subject}</span>`)
          .append(`<small>${e.teacher} — ${e.group_name}</small>`);

        if (isAdmin) {
          const btns = $('<div>').addClass('mt-2 d-flex gap-2');
          btns.append(
            $('<button>')
              .addClass('btn btn-outline-primary btn-sm')
              .html('<i class="bi bi-pencil-fill"></i>')
              .click(() => openEditModal(e.id)),
            $('<button>')
              .addClass('btn btn-outline-danger btn-sm')
              .html('<i class="bi bi-trash-fill"></i>')
              .click(() => deleteSchedule(e.id))
          );
          card.append(btns);
        }

        wrap.append(card);
      });

      col.append(wrap);
      $('#calendar').append(col);
    });
}

/*****************************************************************
 * 1.  В openEditModal  — кладём в input дату в «dd.mm.yyyy»,
 *     а оригинальную строку с днём-недели сохраняем
 *****************************************************************/
function openEditModal(id) {
  const all = $('#calendar').data('rawItems') || [];
  const ent = all.find(x => x.id === id);
  if (!ent) return alert('Пара не найдена.');

  $('#editGroup').val(ent.group_name);
  $('#editSubject').val(ent.subject);
  $('#editTeacher').val(ent.teacher);

  // ent.day => "Чт, 22 мая"  →  22.05.2025
  const [_, d, mName] = ent.day.match(/(\d{1,2}) (\S+)/);
  const monthMap = {
    января:1, февраля:2, марта:3, апреля:4, мая:5, июня:6,
    июля:7, августа:8, сентября:9, октября:10, ноября:11, декабря:12
  };
  const mm = String(monthMap[mName]).padStart(2,'0');
  const dd = String(d).padStart(2,'0');
  const yyyy = new Date().getFullYear();          // год не хранится – берём текущий
  $('#editDate').val(`${dd}.${mm}.${yyyy}`);

  $('#editStartTime').val(ent.start_time);
  $('#editEndTime').val(ent.end_time);
  $('#saveEditBtn').data({ id, origDay: ent.day });   // сохранили исходную строку
  $('#editModal').modal('show');
}

/*****************************************************************
 * 2.  Универсальный helper – превращаем "dd.mm.yyyy" → "Чт, 22 мая"
 *****************************************************************/
function makeDayString(raw) {
  const [d,m,y] = raw.split('.').map(Number);
  const date = new Date(y, m-1, d);
  const wk = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб'];
  const mo = ['', 'января','февраля','марта','апреля','мая',
              'июня','июля','августа','сентября','октября','ноября','декабря'];
  return `${wk[date.getDay()]}, ${d} ${mo[m]}`;
}

/*****************************************************************
 * 3.  При сохранении формируем корректную date-строку
 *****************************************************************/
$('#saveEditBtn').click(async function () {
  const id       = $(this).data('id');
  const origDay  = $(this).data('origDay');      // "Чт, 22 мая"
  const rawDate  = $('#editDate').val().trim();  // может быть пусто

  // Если пользователь стер поле – берём старое значение
  const dayStr = rawDate ? makeDayString(rawDate) : origDay;

  const payload = {
    group_name: $('#editGroup').val().trim(),
    date:       dayStr,
    time:       $('#editStartTime').val() + ' - ' + $('#editEndTime').val(),
    subject:    $('#editSubject').val().trim(),
    teachers:   [ $('#editTeacher').val().trim() ],
    rooms:      [ $('#roomSelect').val() ]
  };

  try {
    await axios.put(`/schedule/${id}`, payload);
    $('#editModal').modal('hide');
    setTimeout(loadRooms, 800);        // даём серверу 0,8 с на пересчёт
  } catch (e) {
    alert('Ошибка сохранения: ' + (e.response?.data?.msg || e));
  }
});

// Удалить запись
async function deleteSchedule(id){
  if(!confirm('Удалить эту запись?')) return;
  try {
    await axios.delete(`/schedule/${id}`);
    loadRooms();
  } catch{
    alert('Ошибка при удалении.');
  }
}

// Управление пользователями
window.promoteUser = async id => {
  if(!confirm('Сделать админом?')) return;
  try {
    await axios.post(`/users/${id}/promote`);
    loadUsers();
  } catch{
    alert('Не удалось назначить администратора');
  }
};

window.demoteUser = async id => {
  if (!confirm('Лишить пользователя прав администратора?')) return;
  try {
    await axios.post(`/users/${id}/demote`);
    loadUsers();
  } catch (e) {
    alert('Не удалось забрать роль: ' + (e.response?.data?.msg || e));
  }
};

window.loadUsers = async () => {
  try {
    const res = await axios.get('/users');
    const tb = $('#usersTableBody').empty();
    res.data.forEach(u => {
      let btn = '';
      if (isAdmin) {
        if (u.role === 'user') {
          btn = `<button class="btn btn-sm btn-warning" onclick="promoteUser(${u.id})">
                   Назначить
                 </button>`;
        } else if (u.role === 'admin') {
          btn = `<button class="btn btn-sm btn-secondary" onclick="demoteUser(${u.id})">
                   Лишить
                 </button>`;
        }
      }
      tb.append(`<tr>
        <td>${u.id}</td>
        <td>${u.email}</td>
        <td>${u.role}</td>
        <td>${btn}</td>
      </tr>`);
    });
  } catch {
    alert('Ошибка загрузки пользователей');
  }
};
