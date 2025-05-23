axios.defaults.baseURL = 'http://127.0.0.1:5000';  // Base URL of backend API

let token = '';
let isAdmin = false;  // Флаг администратора

// Смещение академических недель относительно ISO-нумерации (например, 1-я учебная неделя = ISO-неделя 7)
const ACADEMIC_WEEK_OFFSET = 6;

function parseItemDate(str) {
  const months = {
    'января':1, 'февраля':2, 'марта':3, 'апреля':4, 'мая':5, 'июня':6,
    'июля':7, 'августа':8, 'сентября':9, 'октября':10, 'ноября':11, 'декабря':12
  };
  // str format: "День недели, D Monthname"
  const parts = str.split(',')[1].trim().split(' ');
  const day = parseInt(parts[0], 10);
  const month = months[parts[1]] - 1;
  const year = new Date().getFullYear();
  return new Date(year, month, day);
}

function getDateOfISOWeek(w, y) {
  const simple = new Date(y, 0, 1 + (w - 1) * 7);
  const dow = simple.getDay() || 7;
  if (dow <= 4) {
    simple.setDate(simple.getDate() - dow + 1);
  } else {
    simple.setDate(simple.getDate() + 8 - dow);
  }
  return simple;
}


$(function() {
  // Получение списка групп для автокомплита (используется при добавлении пары)
  axios.get('/groups').then(res => {
    $('#addGroup').autocomplete({ source: res.data });
  });

  // Инициализация datepicker для выбора даты занятия
  $('#addDate').datepicker({
    dateFormat: 'dd.mm.yy',
    regional: 'ru'
  });
  

  // Заполнение выпадающего списка недель (1-19 учебные недели с диапазонами дат)
  const year = new Date().getFullYear();
  for (let w = 1; w <= 19; w++) {
    const isoWeek = w + ACADEMIC_WEEK_OFFSET;
    const start = getDateOfISOWeek(isoWeek, year);
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    const formatDate = d => String(d.getDate()).padStart(2, '0') + '.' + String(d.getMonth()+1).padStart(2, '0');
    $('#roomWeekInput').append(
      `<option value="${w}">${w} (${formatDate(start)} – ${formatDate(end)})</option>`
    );
  }

  // Получение списка кабинетов (если есть отдельный API), иначе извлечение из расписания
  axios.get('/allowed_rooms').then(res => {
    const rooms = res.data;
    rooms.forEach(room => {
      $('#roomSelect').append(`<option value="${room}">${room}</option>`);
    });
  }).catch(() => {
    alert('Не удалось загрузить список кабинетов');
  });
  
  

  // Активация кнопки "Показать" только при выборе кабинета и недели
  $('#roomSelect, #roomWeekInput').change(function() {
    const roomChosen = $('#roomSelect').val();
    const weekChosen = $('#roomWeekInput').val();
    $('#loadRoomsBtn').prop('disabled', !(roomChosen && weekChosen));
  });

  // Обработчик кнопки регистрации
  $('#registerBtn').click(async function register() {
    const email = $('#regEmail').val().trim();
    const password = $('#regPassword').val().trim();
    try {
      await axios.post('/register', { email, password });
      alert('Вы успешно зарегистрировались! Теперь выполните вход.');
      $('#registerModal').modal('hide');
    } catch (e) {
      alert('Ошибка регистрации: ' + (e.response?.data?.msg || e));
    }
  });

  // Обработчик кнопки входа
  $('#loginBtn').click(async function login() {
    const email = $('#email').val().trim();
    const password = $('#password').val().trim();
    try {
      const res = await axios.post('/login', { email, password });
      token = res.data.access_token;
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      console.log("🔐 Токен установлен:", token);
      $('#loginStatus').text('✔ Вход выполнен');
      $('#loginModal').modal('hide');
      // Обновление интерфейса после входа
      $('#loginLink, #registerLink').addClass('d-none');
      $('#logoutLink').removeClass('d-none');
      isAdmin = !!res.data.is_admin;
      if (isAdmin) {
        $('#addBtn').removeClass('d-none');
        $('#deleteBtn').removeClass('d-none');
        $('#manageUsersNav').removeClass('d-none');  // показать пункт меню "Пользователи"
      }      
      // Если уже было загружено расписание до входа, обновим его (чтобы появились кнопки удаления)
      if ($('#roomsBody').children().length > 0) {
        loadRooms();
      }
    } catch (e) {
      alert('Ошибка входа: ' + (e.response?.data?.msg || e));
    }
  });

  // Обработчик кнопки выхода
  $('#logoutLink').click(function logout() {
    // Удаляем токен и заголовок авторизации
    token = '';
    delete axios.defaults.headers.common['Authorization'];
    // Сбрасываем флаг администратора
    isAdmin = false;
    // Скрываем элементы админа
    $('#manageUsersNav').addClass('d-none'); 
    $('#addBtn').addClass('d-none');
    $('.delete-btn').remove();  // убираем кнопки удаления из таблицы
    // Переключаем ссылки навигации
    $('#logoutLink').addClass('d-none');
    $('#loginLink, #registerLink').removeClass('d-none');
  });

  // Обработка показа модального окна добавления пары: обновляем заголовок с номером кабинета
  $('#addModal').on('show.bs.modal', function() {
    const room = $('#roomSelect').val() || '';
    $('#addModalLabel').text(room ? `Добавить пару – ${room}` : 'Добавить пару');
  });

  // Обработчик кнопки добавления пары (в модальном окне)
  $('#addPairBtn').click(async function addPair() {
    const groupName   = $('#addGroup').val().trim();
    const subject     = $('#addSubject').val().trim();
    const teacherName = $('#addTeacher').val().trim();
    const rawDateStr  = $('#addDate').val().trim();
    const startTime   = $('#addStartTime').val();
    const endTime     = $('#addEndTime').val();
    const room        = $('#roomSelect').val();
    const week        = $('#roomWeekInput').val();

    if (!groupName || !subject || !teacherName || !rawDateStr || !startTime || !endTime) {
      return alert('Пожалуйста, заполните все поля формы добавления.');
    }

    // 📅 Преобразуем дату в "Пн, 19 мая"
    const weekdays = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
    const months = [
      '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
      'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ];

    let formattedDay = rawDateStr;
    if (/^\d{2}\.\d{2}\.\d{4}$/.test(rawDateStr)) {
      const [day, month, year] = rawDateStr.split('.').map(Number);
      const d = new Date(year, month - 1, day);
      const weekdayStr = weekdays[d.getDay()];
      const monthStr = months[month];
      formattedDay = `${weekdayStr}, ${day} ${monthStr}`;
    }

    const newEntry = {
      week: Number(week),
      group_name: groupName,
      subject: subject,
      teachers: [teacherName],
      rooms: [room],
      date: formattedDay,
      time: `${startTime} - ${endTime}`
    };

    try {
      const checkRes = await axios.get('/schedule', {
        params: { group: groupName, week: week }
      });
    
      const exists = checkRes.data.some(item =>
        item.date === formattedDay &&
        item.time === `${startTime} - ${endTime}` &&
        item.rooms.includes(room)
      );
    
      if (exists) {
        return alert("❌ Такая пара уже существует в расписании!");
      }
    } catch (e) {
      console.error("Ошибка при проверке дублей:", e);
      return alert("Не удалось проверить дубли");
    }
    

    console.log("Отправляем:", JSON.stringify(newEntry, null, 2));
    console.log("📦 Данные для отправки:");
    console.log({
      week, groupName, subject, teacherName, rawDateStr, startTime, endTime, room
    });
    console.log("📤 Заголовок Authorization:", axios.defaults.headers.common['Authorization']);

    try {
      await axios.post('/schedule', newEntry, {
        headers: { 'Content-Type': 'application/json' }
      });
      console.log("✅ Пара успешно отправлена!");
      $('#addModal').modal('hide');
      loadRooms();
    } catch (e) {
      alert('Ошибка добавления: ' + (e.response?.data?.msg || e.message));
    }
  });

  $('#usersModal').on('show.bs.modal', loadUsers);

});

// Загрузка расписания кабинета по выбранным параметрам
async function loadRooms() {
  console.log("🔄 Загрузка расписания...");
  console.log("   🏫 Кабинет:", $('#roomSelect').val());
  console.log("   📆 Неделя:", $('#roomWeekInput').val());

  const room = $('#roomSelect').val();
  const week = $('#roomWeekInput').val();
  if (!room || !week) {
    return alert('Укажите и кабинет, и неделю.');
  }
  try {
    // Получаем расписание всех занятых кабинетов и фильтруем по выбранному
    const res = await axios.get('/occupied_rooms');
    console.log("📥 Получено расписание (occupied_rooms):", res.data);
    res.data.forEach((item, i) => {
      if (!item.start_time || !item.end_time || !/^\d{2}:\d{2}$/.test(item.start_time)) {
        console.warn(`⚠️ Плохой item #${i}:`, item);
      }
    });
    let data = res.data.filter(item => String(item.week) === String(week) && item.room === room);
    // Сортировка записей по дате и времени начала
    data.sort((a, b) => {
      const dateA = parseItemDate(a.day);
      const dateB = parseItemDate(b.day);
      if (dateA - dateB !== 0) {
        return dateA - dateB;
      }
      // Сравнение по времени начала (часы*60 + минуты)
      const [h1, m1] = a.start_time.split(/[:–—\-]/).map(x => +x);
      const [h2, m2] = b.start_time.split(/[:–—\-]/).map(x => +x);
      return (h1 * 60 + m1) - (h2 * 60 + m2);
    });
    // Заполняем таблицу
    const tbody = $('#roomsBody').empty();
    data.forEach(item => {
      const subj = item.subject || '';
      const teach = item.teacher || '';
      const group = item.group_name || '';
      // Если админ – добавляем кнопку удаления с привязкой по ID
      let actionCell = '';
      if (isAdmin && item.id !== undefined) {
        actionCell = `<button class="btn btn-sm btn-danger delete-btn" onclick="deleteSchedule(${item.id})">Удалить</button>`;
      }
      console.log("📋 Добавляем строку в таблицу:", item);
      tbody.append(`
        <tr>
          <td>${item.day}</td>
          <td>${item.start_time} – ${item.end_time}</td>
          <td>${subj}</td>
          <td>${teach}</td>
          <td>${group}</td>
          <td>${actionCell}</td>
        </tr>
      `);
    });
    // Показываем таблицу после загрузки данных
    $('#roomsTable').removeClass('d-none');
    $('#freeStatus').empty();
    if ($('#freeNow').prop('checked')) {
      const now = new Date();
      let free = true;
      for (let item of data) {
        // Сопоставляем дату занятия с сегодняшней датой
        const classDate = parseItemDate(item.day);
        if (classDate.getDate() === now.getDate() &&
            classDate.getMonth() === now.getMonth() &&
            classDate.getFullYear() === now.getFullYear()) {
          // Сопоставляем время
          const [hStart, mStart] = item.start_time.split(':').map(x => +x);
          const [hEnd, mEnd] = item.end_time.split(':').map(x => +x);
          const classStartMin = hStart * 60 + mStart;
          const classEndMin = hEnd * 60 + mEnd;
          const nowMin = now.getHours() * 60 + now.getMinutes();
          if (nowMin >= classStartMin && nowMin < classEndMin) {
            free = false;
            break;
          }
        }
      }
      if (free) {
        $('#freeStatus').html(`<div class="alert alert-success">Кабинет сейчас свободен</div>`);
      } else {
        $('#freeStatus').html(`<div class="alert alert-danger">Кабинет сейчас занят</div>`);
      }
    }
  } catch {
    alert('Не удалось загрузить расписание кабинета');
  }
}

window.promoteUser = async function(id) {
  if (!confirm("Сделать этого пользователя админом?")) return;
  try {
    await axios.post(`/users/${id}/promote`);
    alert("Пользователь назначен админом");
  } catch (e) {
    console.error("Ошибка при назначении:", e);
    alert("Не удалось назначить");
    return;
  }

  try {
    await loadUsers();  // если здесь ошибка — покажи отдельно
  } catch (e) {
    console.error("Ошибка при обновлении списка пользователей:", e);
    alert("Пользователь назначен, но не удалось обновить список");
  }
};

window.loadUsers = async function() {
  try {
    const res = await axios.get('/users');
    const users = res.data;
    const tbody = $('#usersTableBody').empty();
    users.forEach(u => {
      const btn = (u.role === 'admin') ? '' :
        `<button class="btn btn-sm btn-warning" onclick="promoteUser(${u.id})">Назначить админом</button>`;
      tbody.append(`
        <tr>
          <td>${u.id}</td>
          <td>${u.email}</td>
          <td>${u.role}</td>
          <td>${btn}</td>
        </tr>
      `);
    });
  } catch (e) {
    alert("Ошибка загрузки пользователей");
  }
}

  
// Удаление пары (только для администратора)
async function deleteSchedule(id) {
  console.log("🗑️ Удаляем пару ID:", id);
  if (!confirm('Удалить эту запись?')) return;
  try {
    await axios.delete(`/schedule/${id}`);
    // Перезагружаем расписание после удаления
    loadRooms();
  } catch {
    alert('Ошибка при удалении');
  }
}
