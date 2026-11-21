// The page's language, once every dictionary is in (i18n/*.js): the one
// chosen in this browser (View > Language), else Blender's (meta.lang,
// written at the export), else the browser's, else English. Before any
// view builds its words.
MPI18n.use(MPI18n.pick(M));
document.documentElement.lang = MPI18n.lang;
