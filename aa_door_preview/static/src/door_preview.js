/* THE SERIES 1200 PREVIEW: ONE MODEL, THE COLOURS SWAPPED IN THE BROWSER.
 *
 * What the live site does today (read off davidaaigd.sirv.com/3d/ on
 * 2026-10-26): one .glb PER COMBINATION of frame finish and glass colour.
 * Thirteen files, ~8.8 MB each for the painted ones and ~10.0 MB for the
 * woodgrain ones, about 118 MB in all, and clicking a colour downloads a
 * whole new door.
 *
 * It does not need to. Every one of those files holds the SAME single mesh -
 * seven primitives, same byte count to within a few dozen bytes - and differs
 * only in what its materials are set to. The materials are named by role,
 * which is what makes this possible:
 *
 *     Silver            the hardware and track          left alone
 *     Frame_white       the door's frame                 recoloured
 *     Frane_Black       ditto, in the Black files        (his typo, matched)
 *     Frame_woodgrain   ditto, with a texture
 *     Frame_bronze      a piece that is DARK in every
 *                       one of his files                 left alone
 *     Glass_clear ...   the glazing                      recoloured
 *     Blue_Circle       unidentified - a badge?          left alone
 *     White_Circle      ditto
 *
 * So: load one file, keep it, and set colours on the materials. One 8.8 MB
 * download instead of thirteen, every colour change instant, and all twenty
 * combinations work - including the SEVEN that have no file on Sirv today and
 * therefore cannot be shown on the live site at all.
 *
 * The numbers below are not invented. Every base colour, metalness,
 * roughness and transmission factor was read out of the glTF material
 * definitions in his own files, and baseColorFactor in glTF is LINEAR, which
 * is why they go in through Color.fromArray and not through a hex string.
 */

(function (global) {
  "use strict";

  var THREE = global.THREE;

  /* Which materials are the door's frame, and which are left as they came.
   * Frame_bronze is dark (0.02 linear, near black) in ALL of his files,
   * including the white and the woodgrain ones, so it is a trim piece and not
   * the frame - painting it would change a door he has already approved. */
  var FRAME_RE = /^fra[mn]e_(white|black|woodgrain)$/i;
  var GLASS_RE = /^glass/i;

  var FRAMES = [
    { id: "white",  name: "White",  swatch: "#f1f1ef",
      linear: [1, 1, 1],                        metalness: 0.282, roughness: 0.550 },
    { id: "bronze", name: "Bronze", swatch: "#2c2a28",
      linear: [0.0204, 0.0201, 0.0195],         metalness: 0.179, roughness: 0.450 },
    { id: "black",  name: "Black",  swatch: "#111214",
      linear: [0, 0, 0],                        metalness: 0.282, roughness: 0.095 },
    { id: "wood",   name: "Wood",   swatch: "#b65c14",
      texture: true,                            metalness: 0.282, roughness: 0.418 }
  ];

  var GLASSES = [
    { id: "clear",  name: "Clear",  swatch: "#e6e6e6",
      linear: [0.8, 0.8, 0.8],                  transmission: 1.000, roughness: 0.001 },
    { id: "white",  name: "White",  swatch: "#dde6dc",
      linear: [0.7323, 0.8001, 0.7270],         transmission: 0.578, roughness: 0.063 },
    { id: "green",  name: "Green",  swatch: "#78c792",
      linear: [0.1946, 0.5841, 0.3005],         transmission: 0.578, roughness: 0.063 },
    { id: "bronze", name: "Bronze", swatch: "#a45633",
      linear: [0.3771, 0.0895, 0.0278],         transmission: 0.578, roughness: 0.063 },
    { id: "grey",   name: "Grey",   swatch: "#a4a4a4",
      linear: [0.3771, 0.3771, 0.3771],         transmission: 0.578, roughness: 0.063 }
  ];

  /* The combinations with no .glb on Sirv as of 2026-10-26. Picking one of
   * these on the live site asks for a file that answers 404. They are shown
   * here because one model can render them. */
  var NO_FILE_TODAY = {
    "white_white": 1, "white_green": 1, "white_bronze": 1, "white_grey": 1,
    "bronze_white": 1, "wood_clear": 1, "wood_white": 1
  };

  var DEFAULT_MODEL = "https://davidaaigd.sirv.com/3d/White_Clear.glb";

  /* ---- a studio environment, generated rather than downloaded --------- */

  function studioEnv() {
    function face(stops) {
      var c = document.createElement("canvas");
      c.width = c.height = 128;
      var g = c.getContext("2d");
      var grad = g.createLinearGradient(0, 0, 0, 128);
      for (var i = 0; i < stops.length; i++) {
        grad.addColorStop(stops[i][0], stops[i][1]);
      }
      g.fillStyle = grad;
      g.fillRect(0, 0, 128, 128);
      return c;
    }
    var side = face([[0, "#b3bec7"], [0.46, "#737d86"], [0.54, "#2b3035"], [1, "#14171a"]]);
    var up = face([[0, "#eaf0f4"], [1, "#c3ccd4"]]);
    var down = face([[0, "#1c2023"], [1, "#0d1012"]]);
    var tex = new THREE.CubeTexture([side, side, up, down, side, side]);
    tex.encoding = THREE.sRGBEncoding;
    tex.needsUpdate = true;
    return tex;
  }

  /* ---- DOM ------------------------------------------------------------ */

  function el(tag, cls, parent) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (parent) { parent.appendChild(node); }
    return node;
  }

  var EXPAND_ICON =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"' +
    ' stroke-linecap="square" aria-hidden="true">' +
    '<path d="M9 4H4v5M20 9V4h-5M15 20h5v-5M4 15v5h5"></path>' +
    '<path d="M4 4l6 6M20 4l-6 6M20 20l-6-6M4 20l6-6"></path></svg>';

  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

  /* ---- the viewer ----------------------------------------------------- */

  function mount(host, options) {
    options = options || {};

    var modelUrl = options.model || host.getAttribute("data-model") || DEFAULT_MODEL;
    var woodUrl = options.wood || host.getAttribute("data-wood") || "./woodgrain.jpg";
    var showMissing = (host.getAttribute("data-flag-missing") || "") === "1";

    if (!THREE || !THREE.GLTFLoader) {
      host.classList.add("aadp", "aadp--failed");
      el("p", "aadp__message", host).textContent =
        "The 3D preview could not load its renderer.";
      return null;
    }

    host.classList.add("aadp");

    var canvas = el("canvas", "aadp__canvas", host);
    var readout = el("p", "aadp__readout", host);
    var tools = el("div", "aadp__tools", host);

    var resetBtn = el("button", "aadp__tool", tools);
    resetBtn.type = "button";
    resetBtn.textContent = "Reset view";

    var expandBtn = el("button", "aadp__tool aadp__tool--icon", tools);
    expandBtn.type = "button";
    expandBtn.innerHTML = EXPAND_ICON;
    expandBtn.setAttribute("aria-label", "Fullscreen");

    var panel = el("div", "aadp__panel", host);
    var loader = el("div", "aadp__loading", host);
    var loaderText = el("p", "aadp__loading-text", loader);
    loaderText.textContent = "Loading the door…";

    /* ---- renderer --------------------------------------------------- */

    var renderer = new THREE.WebGLRenderer({
      canvas: canvas, antialias: true, alpha: true
    });
    renderer.setPixelRatio(Math.min(global.devicePixelRatio || 1, 2));
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(32, 1.6, 0.01, 2000);
    var env = studioEnv();
    scene.environment = env;

    scene.add(new THREE.HemisphereLight(0xccd6de, 0x2b3034, 0.6));

    var key = new THREE.DirectionalLight(0xffffff, 1.5);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.bias = -0.0008;
    key.shadow.radius = 3;
    scene.add(key);

    var fill = new THREE.DirectionalLight(0xdce6ee, 0.5);
    scene.add(fill);

    var rim = new THREE.DirectionalLight(0xffffff, 0.35);
    scene.add(rim);

    var floor = new THREE.Mesh(
      new THREE.PlaneGeometry(1, 1),
      new THREE.ShadowMaterial({ color: 0x000000, opacity: 0.42 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    floor.visible = false;
    scene.add(floor);

    /* ---- state ------------------------------------------------------ */

    var frameMats = [];
    var glassMats = [];
    var woodTexture = null;
    var frame = FRAMES[0];
    var glass = GLASSES[0];

    var HOME = { azimuth: -0.38, polar: 1.44, zoom: 1 };
    var want = { azimuth: HOME.azimuth, polar: HOME.polar, zoom: HOME.zoom };
    var have = { azimuth: HOME.azimuth, polar: HOME.polar, zoom: HOME.zoom };
    var target = new THREE.Vector3();
    var span = new THREE.Vector3(1, 1, 1);
    var baseDistance = 10;

    /* ---- applying a choice ------------------------------------------ */

    function applyFrame(choice) {
      frame = choice;
      if (choice.texture) {
        if (!woodTexture) {
          woodTexture = new THREE.TextureLoader().load(woodUrl);
          woodTexture.flipY = false;                 /* glTF UV convention */
          woodTexture.encoding = THREE.sRGBEncoding;
          woodTexture.wrapS = woodTexture.wrapT = THREE.RepeatWrapping;
        }
      }
      frameMats.forEach(function (m) {
        m.map = choice.texture ? woodTexture : null;
        if (choice.texture) {
          m.color.setRGB(1, 1, 1);
        } else {
          m.color.fromArray(choice.linear);
        }
        m.metalness = choice.metalness;
        m.roughness = choice.roughness;
        m.needsUpdate = true;
      });
      label();
    }

    function applyGlass(choice) {
      glass = choice;
      glassMats.forEach(function (m) {
        m.color.fromArray(choice.linear);
        m.roughness = choice.roughness;
        if ("transmission" in m) { m.transmission = choice.transmission; }
        m.needsUpdate = true;
      });
      label();
    }

    function label() {
      var text = frame.name + " frame · " + glass.name + " glass";
      if (showMissing && NO_FILE_TODAY[frame.id + "_" + glass.id]) {
        text += " · no .glb for this on Sirv today";
      }
      readout.textContent = text;
    }

    /* ---- chips ------------------------------------------------------ */

    function group(title, choices, initial, onPick) {
      var wrap = el("div", "aadp__group", panel);
      var head = el("span", "aadp__group-label", wrap);
      head.textContent = title;
      var chips = el("div", "aadp__chips", wrap);
      chips.setAttribute("role", "radiogroup");
      chips.setAttribute("aria-label", title);

      var buttons = [];
      choices.forEach(function (choice, index) {
        var b = el("button", "aadp__chip", chips);
        b.type = "button";
        b.id = "aadp-" + title.toLowerCase().replace(/[^a-z]+/g, "-") + "-" + choice.id;
        b.setAttribute("role", "radio");
        b.setAttribute("aria-checked", index === initial ? "true" : "false");
        var dot = el("span", "aadp__dot", b);
        dot.style.background = choice.swatch;
        b.appendChild(document.createTextNode(choice.name));
        b.addEventListener("click", function () {
          buttons.forEach(function (other) {
            other.setAttribute("aria-checked", "false");
          });
          b.setAttribute("aria-checked", "true");
          onPick(choice);
        });
        buttons.push(b);
      });
    }

    group("Frame finish", FRAMES, 0, applyFrame);
    group("Glass", GLASSES, 0, applyGlass);

    /* ---- the model -------------------------------------------------- */

    new THREE.GLTFLoader().load(modelUrl, function (gltf) {
      var model = gltf.scene;

      model.traverse(function (node) {
        if (!node.isMesh) { return; }
        node.castShadow = true;
        node.receiveShadow = true;
        var mats = Array.isArray(node.material) ? node.material : [node.material];
        mats.forEach(function (m) {
          if (!m) { return; }
          m.envMap = env;
          var name = m.name || "";
          if (GLASS_RE.test(name)) {
            m.envMapIntensity = 1.25;
            m.transparent = true;
            m.side = THREE.DoubleSide;
            if (glassMats.indexOf(m) === -1) { glassMats.push(m); }
          } else if (FRAME_RE.test(name)) {
            m.envMapIntensity = 0.9;
            if (frameMats.indexOf(m) === -1) { frameMats.push(m); }
          } else {
            m.envMapIntensity = 0.85;
          }
        });
      });

      /* CENTRE AND FRAME WHATEVER ARRIVED. The model's units, origin and
       * orientation are whoever exported it's business, so the camera is
       * fitted to the bounding box rather than to numbers typed in here -
       * which is also what lets a replacement model drop straight in. */
      var box = new THREE.Box3().setFromObject(model);
      box.getCenter(target);
      box.getSize(span);
      model.position.y -= box.min.y;      /* stand it on the floor */
      target.y -= box.min.y;
      scene.add(model);

      var reach = Math.max(span.x, span.y, span.z);
      floor.scale.set(reach * 12, reach * 12, 1);
      floor.position.y = 0.0015 * reach;
      floor.visible = true;

      key.position.set(reach * 0.9, reach * 1.5, reach * 1.1);
      key.shadow.camera.left = -reach;
      key.shadow.camera.right = reach;
      key.shadow.camera.top = reach;
      key.shadow.camera.bottom = -reach * 0.6;
      key.shadow.camera.near = reach * 0.05;
      key.shadow.camera.far = reach * 6;
      key.shadow.camera.updateProjectionMatrix();
      fill.position.set(-reach * 1.1, reach * 0.7, reach * 0.7);
      rim.position.set(-reach * 0.3, reach * 0.5, -reach * 1.2);

      camera.near = reach / 500;
      camera.far = reach * 60;

      /* Look a little above the middle, so the control panel along the
       * bottom of the frame does not sit over the door. */
      target.y += span.y * 0.06;

      applyFrame(FRAMES[0]);
      applyGlass(GLASSES[0]);
      resize();
      loader.hidden = true;

    }, function (progress) {
      if (progress && progress.total) {
        var pct = Math.round(progress.loaded / progress.total * 100);
        loaderText.textContent = "Loading the door… " + pct + "%";
      } else if (progress && progress.loaded) {
        loaderText.textContent = "Loading the door… " +
          (progress.loaded / 1048576).toFixed(1) + " MB";
      }
    }, function () {
      loaderText.textContent = "That model could not be loaded.";
    });

    /* ---- orbit ------------------------------------------------------ */

    function fit() {
      var vFov = camera.fov * Math.PI / 180;
      var forHeight = (span.y * 1.42 / 2) / Math.tan(vFov / 2);
      var forWidth = (span.x * 1.14 / 2) / (Math.tan(vFov / 2) * camera.aspect);
      baseDistance = Math.max(forHeight, forWidth, span.z * 1.5);
    }

    function place() {
      var d = baseDistance * have.zoom;
      var sp = Math.sin(have.polar);
      camera.position.set(
        target.x + d * sp * Math.sin(have.azimuth),
        target.y + d * Math.cos(have.polar),
        target.z + d * sp * Math.cos(have.azimuth)
      );
      camera.lookAt(target);
    }

    var pointers = {};
    var lastPinch = 0;

    canvas.addEventListener("pointerdown", function (e) {
      canvas.setPointerCapture(e.pointerId);
      pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
      canvas.classList.add("aadp--dragging");
      lastPinch = 0;
    });

    canvas.addEventListener("pointermove", function (e) {
      var prev = pointers[e.pointerId];
      if (!prev) { return; }
      var ids = Object.keys(pointers);

      if (ids.length >= 2) {
        pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
        var a = pointers[ids[0]], b = pointers[ids[1]];
        var gap = Math.sqrt((a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y));
        if (lastPinch && gap) { zoomBy(lastPinch / gap); }
        lastPinch = gap;
        return;
      }

      var dx = e.clientX - prev.x;
      var dy = e.clientY - prev.y;
      pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
      want.azimuth -= dx * 0.0062;
      want.polar = clamp(want.polar - dy * 0.0052, 0.22, 1.66);
    });

    function release(e) {
      delete pointers[e.pointerId];
      if (!Object.keys(pointers).length) {
        canvas.classList.remove("aadp--dragging");
      }
      lastPinch = 0;
    }

    canvas.addEventListener("pointerup", release);
    canvas.addEventListener("pointercancel", release);

    canvas.addEventListener("wheel", function (e) {
      e.preventDefault();
      zoomBy(1 + (e.deltaY > 0 ? 0.09 : -0.09));
    }, { passive: false });

    function zoomBy(factor) {
      want.zoom = clamp(want.zoom * factor, 0.40, 2.2);
    }

    resetBtn.addEventListener("click", function () {
      want.azimuth = HOME.azimuth;
      want.polar = HOME.polar;
      want.zoom = HOME.zoom;
    });

    /* ---- fullscreen, with an in-page fallback ----------------------- */

    var expanded = false;

    function setExpanded(on) {
      expanded = on;
      host.classList.toggle("aadp--expanded", on);
      document.body.style.overflow = on ? "hidden" : "";
      expandBtn.setAttribute("aria-label", on ? "Exit fullscreen" : "Fullscreen");
      resize();
    }

    expandBtn.addEventListener("click", function () {
      if (document.fullscreenElement) { document.exitFullscreen(); return; }
      if (expanded) { setExpanded(false); return; }
      if (host.requestFullscreen) {
        var attempt = host.requestFullscreen();
        if (attempt && attempt.catch) {
          attempt.catch(function () { setExpanded(true); });
        }
        return;
      }
      setExpanded(true);
    });

    document.addEventListener("fullscreenchange", function () {
      var on = !!document.fullscreenElement;
      expandBtn.setAttribute("aria-label", on ? "Exit fullscreen" : "Fullscreen");
      resize();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && expanded) { setExpanded(false); }
    });

    /* ---- loop ------------------------------------------------------- */

    function resize() {
      var w = host.clientWidth || 1;
      var h = host.clientHeight || 1;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      fit();
    }

    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(resize).observe(host);
    }
    global.addEventListener("resize", resize);

    resize();
    place();
    label();

    (function tick() {
      have.azimuth += (want.azimuth - have.azimuth) * 0.18;
      have.polar += (want.polar - have.polar) * 0.18;
      have.zoom += (want.zoom - have.zoom) * 0.18;
      place();
      renderer.render(scene, camera);
      global.requestAnimationFrame(tick);
    })();

    return {
      setFrame: function (id) {
        FRAMES.forEach(function (f) { if (f.id === id) { applyFrame(f); } });
      },
      setGlass: function (id) {
        GLASSES.forEach(function (g) { if (g.id === id) { applyGlass(g); } });
      }
    };
  }

  function auto() {
    var hosts = document.querySelectorAll("[data-aa-door-preview]");
    for (var i = 0; i < hosts.length; i++) { mount(hosts[i], {}); }
  }

  global.AADoorPreview = {
    mount: mount,
    FRAMES: FRAMES,
    GLASSES: GLASSES,
    NO_FILE_TODAY: NO_FILE_TODAY
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", auto);
  } else {
    auto();
  }
})(window);
