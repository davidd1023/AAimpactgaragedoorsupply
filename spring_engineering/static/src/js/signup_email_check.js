/** @odoo-module **/

// TELL THEM WHILE THEY ARE STILL LOOKING AT THE BOX.
//
// The server refuses a bad address - see controllers/signup.py, which is the
// only check that counts - but being refused after pressing Sign up means
// reading the form again to find out which field was wrong. A browser already
// knows the moment the box loses focus; it just will not say so until the
// form is submitted.
//
// So the answer is given on the way out of the field, in the page's own
// style rather than a native bubble, and taken back the moment they start
// fixing it. Nothing here blocks the form: the submit button still works,
// and the server still has the last word.
const BOXES = 'input[name="login"][type="email"]';
const MESSAGE = "aa_email_note";

function noteFor(el) {
    let note = el.parentElement?.querySelector("." + MESSAGE);

    if (!note) {
        note = document.createElement("div");
        note.className = MESSAGE + " invalid-feedback d-block small";
        el.insertAdjacentElement("afterend", note);
    }

    return note;
}

function complain(el) {
    // An empty box is not yet a mistake - they may simply not have started.
    if (!el.value.trim()) {
        return forgive(el);
    }

    if (el.checkValidity()) {
        return forgive(el);
    }

    el.classList.add("is-invalid");
    noteFor(el).textContent =
        "That does not look like an email address - please check it.";
}

function forgive(el) {
    el.classList.remove("is-invalid");

    const note = el.parentElement?.querySelector("." + MESSAGE);

    if (note) {
        note.remove();
    }
}

// Capture, because focusout is the one that bubbles and the field may be
// drawn long after this file runs - the login and signup pages are rendered
// by the server and swapped around by the website editor.
document.addEventListener("focusout", (ev) => {
    if (ev.target?.matches?.(BOXES)) {
        complain(ev.target);
    }
}, true);

document.addEventListener("input", (ev) => {
    if (ev.target?.matches?.(BOXES)) {
        forgive(ev.target);
    }
}, true);
