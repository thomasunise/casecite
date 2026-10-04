// Self-hosted fonts. The files ship in the build output, so a self-hosted
// instance makes no request to a font CDN and works without internet access.
// Each stylesheet declares unicode-range subsets; the browser downloads only
// the ones a page actually uses.
import '@fontsource/inter/300.css';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';
import '@fontsource/source-serif-4/500.css';
import '@fontsource/source-serif-4/600.css';
