// Renders the deck icons (react-icons -> PNG) into .tmp/icons. Run from repo root:
//   NODE_PATH=.tmp/deckgen/node_modules node docs/deck_src/make_icons.js
const fs = require("fs");
const path = require("path");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa");

const OUT = path.resolve(__dirname, "..", "..", ".tmp", "icons");
fs.mkdirSync(OUT, { recursive: true });
const names = { bolt: fa.FaBolt, quote: fa.FaQuoteLeft, clock: fa.FaClock, phone: fa.FaPhoneAlt, cog: fa.FaCog,
  check: fa.FaCheckCircle, link: fa.FaLink, db: fa.FaDatabase, shield: fa.FaShieldAlt, brain: fa.FaBrain,
  search: fa.FaSearch, layer: fa.FaLayerGroup, mic: fa.FaMicrophone, route: fa.FaRoute, doc: fa.FaFileAlt,
  server: fa.FaServer, flask: fa.FaFlask, warn: fa.FaExclamationTriangle, rocket: fa.FaRocket, users: fa.FaUsers,
  list: fa.FaListOl, sync: fa.FaSyncAlt, docker: fa.FaDocker, python: fa.FaPython, lock: fa.FaLock,
  headset: fa.FaHeadset, robot: fa.FaRobot, sitemap: fa.FaSitemap, times: fa.FaTimesCircle, star: fa.FaStar,
  globe: fa.FaGlobeAsia, chart: fa.FaChartBar, user: fa.FaUserCircle, mobile: fa.FaMobileAlt };
(async () => {
  for (const [k, Comp] of Object.entries(names)) {
    for (const [suffix, color] of [["w", "#FFFFFF"], ["p", "#6D28D9"]]) {
      const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { color, size: 256 }));
      await sharp(Buffer.from(svg)).resize(256, 256).png().toFile(path.join(OUT, `${k}_${suffix}.png`));
    }
  }
  console.log("icons ->", OUT);
})();
