import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://mixz.wulab.tech',
  output: 'static',
  build: {
    format: 'file'
  }
});
