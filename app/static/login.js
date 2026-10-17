document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('loginForm');
  const usernameInput = document.getElementById('username');
  const passwordInput = document.getElementById('password');
  const submitBtn = document.getElementById('submitBtn');
  const errorBanner = document.getElementById('errorBanner');
  const infoBanner = document.getElementById('infoBanner');

  const params = new URLSearchParams(window.location.search);
  if (params.get('expired') === '1') {
    infoBanner.textContent = 'Tu sesión ha expirado. Por favor, inicia sesión nuevamente.';
    infoBanner.classList.remove('hidden');
  }

  function showError(message) {
    errorBanner.textContent = message;
    errorBanner.classList.remove('hidden');
  }

  function clearMessages() {
    errorBanner.classList.add('hidden');
    infoBanner.classList.add('hidden');
  }

  const recoveryForm = document.getElementById('recoveryForm');
  const recoveryFeedback = document.getElementById('recoveryFeedback');
  document.getElementById('showRecovery').addEventListener('click', () => {
    form.classList.add('hidden');
    recoveryForm.classList.remove('hidden');
    document.getElementById('showRecovery').classList.add('hidden');
    document.getElementById('recoveryUsername').value = usernameInput.value;
    clearMessages();
  });
  document.getElementById('hideRecovery').addEventListener('click', () => {
    recoveryForm.reset();
    recoveryForm.classList.add('hidden');
    form.classList.remove('hidden');
    document.getElementById('showRecovery').classList.remove('hidden');
  });
  recoveryForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    recoveryFeedback.textContent = '';
    const username = document.getElementById('recoveryUsername').value.trim();
    const recovery_code = document.getElementById('recoveryCode').value.trim();
    const new_password = document.getElementById('recoveryNewPassword').value;
    if (new_password.length < 16 ||
        new_password !== document.getElementById('recoveryConfirmPassword').value) {
      recoveryFeedback.textContent = 'La contraseña debe tener 16 caracteres y coincidir.';
      return;
    }
    const button = document.getElementById('recoverySubmit');
    button.disabled = true;
    try {
      const response = await fetch('/api/auth/recover', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username, recovery_code, new_password}),
      });
      if (response.ok) {
        recoveryForm.reset();
        recoveryForm.classList.add('hidden');
        form.classList.remove('hidden');
        document.getElementById('showRecovery').classList.remove('hidden');
        infoBanner.textContent = 'Contraseña actualizada. Inicia sesión con la nueva.';
        infoBanner.classList.remove('hidden');
      } else {
        recoveryFeedback.textContent = response.status === 429
          ? 'Demasiados intentos. Espera antes de reintentar.'
          : 'Usuario o código de recuperación incorrecto.';
      }
    } catch (_) {
      recoveryFeedback.textContent = 'Error de conexión.';
    } finally { button.disabled = false; }
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearMessages();

    const username = usernameInput.value.trim();
    const password = passwordInput.value;

    if (!username || !password) {
      showError('Usuario o contraseña incorrectos.');
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Verificando...';

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ username, password }),
      });

      if (response.ok) {
        window.location.href = '/';
      } else if (response.status === 429) {
        const errorData = await response.json().catch(() => null);
        showError(errorData?.detail || 'Demasiados intentos de acceso fallidos. Por favor, inténtelo de nuevo más tarde.');
      } else {
        showError('Usuario o contraseña incorrectos.');
      }
    } catch (err) {
      showError('Error de conexión con el servidor. Inténtalo de nuevo.');
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Iniciar sesión';
    }
  });
});
