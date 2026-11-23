// The page's language, once every dictionary is in (i18n/*.js): the one
// chosen in this browser (View > Language), else Blender's (meta.lang,
// written at the export), else the browser's, else English. Before any
// view builds its words.
MPI18n.use(MPI18n.pick(M));
document.documentElement.lang = MPI18n.lang;
// A word Blender sent (a farm step, an error, a note): translated when the
// dictionary has it, else as sent. Never a key of T('...'): the server's.
// A step's count at its end (its frames done, of all) kept as it is.
function TS(s) {
  if (!s) return s;
  const m = String(s).match(/^(.*?)( \d+\/\d+)$/);
  return m ? T(m[1]) + m[2] : T(String(s));
}
