/* login.js — client-side field checks only. Server still validates. */
(function () {
  "use strict";

  function showError(form, message) {
    var existing = form.querySelector(".flash.err");
    if (!existing) {
      existing = document.createElement("p");
      existing.className = "flash err";
      form.insertBefore(existing, form.firstChild);
    }
    existing.textContent = message;
  }

  function bind(formId, checker) {
    var form = document.getElementById(formId);
    if (!form) {
      return;
    }
    form.addEventListener("submit", function (event) {
      var message = checker(new FormData(form));
      if (message) {
        event.preventDefault();
        showError(form, message);
      }
    });
  }

  bind("login-form", function (data) {
    var username = String(data.get("username") || "");
    var password = String(data.get("password") || "");
    if (!/^[A-Za-z][A-Za-z0-9_]{2,31}$/.test(username)) {
      return "Username must start with a letter and be 3-32 letters, digits, or underscores.";
    }
    if (password.length < 10) {
      return "Password must be at least 10 characters.";
    }
    return "";
  });

  bind("register-form", function (data) {
    var username = String(data.get("username") || "");
    var email = String(data.get("email") || "");
    var password = String(data.get("password") || "");
    var confirm = String(data.get("confirm") || "");
    if (!/^[A-Za-z][A-Za-z0-9_]{2,31}$/.test(username)) {
      return "Username must start with a letter and be 3-32 letters, digits, or underscores.";
    }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      return "Enter a valid email address.";
    }
    if (password.length < 10 || !/[A-Za-z]/.test(password) || !/\d/.test(password)) {
      return "Password must be at least 10 characters and include a letter and a number.";
    }
    if (password !== confirm) {
      return "Passwords do not match.";
    }
    return "";
  });
})();
