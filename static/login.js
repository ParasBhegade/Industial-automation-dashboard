// PASSWORD VISIBILITY TOGGLE
const togglePassword = document.getElementById('togglePassword');
const passwordField = document.getElementById('password');

if (togglePassword && passwordField) {
  togglePassword.addEventListener('click', () => {
    const type = passwordField.getAttribute('type') === 'password' ? 'text' : 'password';
    passwordField.setAttribute('type', type);
    togglePassword.textContent = type === 'password' ? '👁️' : '🙈';
  });
}

// SIMPLE LOGIN VALIDATION
const form = document.getElementById('loginForm');
if (form) {
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value.trim();

    if (!email || !password) {
      alert('Please enter your email and password.');
      return;
    }

    // Placeholder for backend connection
    alert(`Welcome back, ${email}!`);
  });
}
