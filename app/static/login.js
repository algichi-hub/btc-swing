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
