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

// FORM VALIDATION
const form = document.getElementById('registerForm');
if (form) {
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const fullname = document.getElementById('fullname').value.trim();
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value.trim();
    const confirmPassword = document.getElementById('confirmPassword').value.trim();

    if (!fullname || !email || !password || !confirmPassword) {
      alert('Please fill all the fields.');
      return;
    }
    if (password !== confirmPassword) {
      alert('Passwords do not match!');
      return;
    }

    // Placeholder for backend connection
    alert(`Welcome, ${fullname}! Registration successful.`);
    window.location.href = 'login.html';
  });
}
