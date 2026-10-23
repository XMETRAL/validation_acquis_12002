/* Interactions côté client - Validation d'acquis */

// --- Bascule thème clair / sombre (persistée) ------------------------------
(function () {
  var btn = document.getElementById("theme-toggle");
  if (!btn) return;
  function refresh() {
    var dark = document.documentElement.getAttribute("data-theme") === "dark";
    btn.textContent = dark ? "☀" : "☾";
    btn.setAttribute("aria-label", dark ? "Passer en mode clair" : "Passer en mode sombre");
  }
  btn.addEventListener("click", function () {
    var dark = document.documentElement.getAttribute("data-theme") === "dark";
    var next = dark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("va-theme", next); } catch (e) {}
    refresh();
  });
  refresh();
})();

// --- Copie d'une URL dans le presse-papier ---------------------------------
document.querySelectorAll("[data-copy]").forEach(function (btn) {
  btn.addEventListener("click", function () {
    var target = document.querySelector(btn.getAttribute("data-copy"));
    if (!target) return;
    target.select();
    var done = function () {
      var old = btn.textContent;
      btn.textContent = "Copié ✓";
      setTimeout(function () { btn.textContent = old; }, 1500);
    };
    if (navigator.clipboard) {
      navigator.clipboard.writeText(target.value).then(done, function () {
        document.execCommand("copy"); done();
      });
    } else {
      document.execCommand("copy"); done();
    }
  });
});

// --- Zone de dépôt d'image (drag & drop) -----------------------------------
(function () {
  var dz = document.getElementById("dropzone");
  var input = document.getElementById("image-input");
  if (!dz || !input) return;
  var preview = document.getElementById("image-preview");
  var hint = document.getElementById("dz-hint");

  function showFile(file) {
    if (!file || !file.type.startsWith("image/")) return;
    var reader = new FileReader();
    reader.onload = function (e) {
      if (preview) {
        preview.src = e.target.result;
        preview.style.display = "block";
      }
      if (hint) hint.textContent = file.name;
      var rm = document.getElementById("remove-image");
      if (rm) rm.checked = false;
    };
    reader.readAsDataURL(file);
  }

  dz.addEventListener("click", function () { input.click(); });
  input.addEventListener("change", function () {
    if (input.files.length) showFile(input.files[0]);
  });
  ["dragenter", "dragover"].forEach(function (ev) {
    dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add("drag"); });
  });
  ["dragleave", "drop"].forEach(function (ev) {
    dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove("drag"); });
  });
  dz.addEventListener("drop", function (e) {
    var files = e.dataTransfer.files;
    if (files.length) {
      input.files = files;
      showFile(files[0]);
    }
  });
})();

// --- Éditeur de réponses (ajout / suppression de lignes) -------------------
(function () {
  var list = document.getElementById("choice-list");
  var addBtn = document.getElementById("add-choice");
  if (!list || !addBtn) return;

  function bindRow(row) {
    var cb = row.querySelector(".ck input[type=checkbox]");
    var hidden = row.querySelector("input.correct-val");
    if (cb && hidden) {
      cb.addEventListener("change", function () { hidden.value = cb.checked ? "1" : "0"; });
    }
    var del = row.querySelector(".del-choice");
    if (del) {
      del.addEventListener("click", function () {
        if (list.querySelectorAll(".choice-editor").length > 2) {
          row.remove();
        } else {
          alert("Deux réponses minimum sont nécessaires.");
        }
      });
    }
  }

  function newRow() {
    var row = document.createElement("div");
    row.className = "choice-editor";
    row.innerHTML =
      '<input type="text" name="choice_text" placeholder="Texte de la réponse" maxlength="500">' +
      '<label class="ck"><input type="checkbox"> Correcte</label>' +
      '<button type="button" class="btn btn-sm btn-danger del-choice">✕</button>' +
      '<input type="hidden" name="choice_is_correct" value="0" class="correct-val">';
    return row;
  }

  addBtn.addEventListener("click", function () {
    var row = newRow();
    list.appendChild(row);
    bindRow(row);
  });

  list.querySelectorAll(".choice-editor").forEach(bindRow);
})();

// --- Images de question : agrandissement plein écran au clic ---------------
// 1er clic : image ajustée à l'écran ; clic sur l'image : taille réelle
// (défilement) ; clic à côté, bouton × ou Échap : fermeture.
(function () {
  var box = null;
  function fermer() {
    if (box) { box.remove(); box = null; document.body.style.overflow = ""; }
  }
  function ouvrir(src, alt) {
    fermer();
    box = document.createElement("div");
    box.className = "lightbox";
    box.innerHTML = '<button type="button" class="lightbox-close" aria-label="Fermer">×</button>';
    var img = document.createElement("img");
    img.src = src; img.alt = alt || "";
    box.appendChild(img);
    box.addEventListener("click", function (e) {
      if (e.target === img) { box.classList.toggle("full"); } else { fermer(); }
    });
    document.body.appendChild(box);
    document.body.style.overflow = "hidden";
  }
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") fermer(); });
  document.querySelectorAll("img.q-image").forEach(function (img) {
    img.addEventListener("click", function () {
      if (img.getAttribute("src")) ouvrir(img.src, img.alt);
    });
  });
})();

// --- Quiz : mise en évidence de la proposition cochée ----------------------
// (bouton radio : décocher l'autre ne déclenche pas « change » sur lui,
//  on rafraîchit donc toutes les propositions à chaque changement)
var quizInputs = document.querySelectorAll(".choice input");
var applyAll = function () {
  quizInputs.forEach(function (input) {
    var box = input.closest(".choice");
    if (input.checked) box.classList.add("selected");
    else box.classList.remove("selected");
  });
};
quizInputs.forEach(function (input) { input.addEventListener("change", applyAll); });
applyAll();
