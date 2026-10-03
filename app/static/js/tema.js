/* Aplica o tema salvo antes da primeira pintura, para não piscar. Roda como script clássico no <head>. */
(function () {
  try {
    var tema = localStorage.getItem("tema");
    if (tema === "claro" || tema === "escuro") {
      document.documentElement.setAttribute("data-tema", tema);
    }
  } catch (e) {
    /* armazenamento indisponível (janela privada etc.): segue o tema do sistema */
  }
})();
