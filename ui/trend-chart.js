/* Offline SVG renderer for the calibration scatter/line configuration in app.js.
 * All labels and tooltips are text nodes. No remote code or HTML parsing.
 */
class CalibrationChart {
  constructor(canvas, config) {
    this.canvas = canvas;
    this.config = config;
    this.hidden = new Set();
    this.svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    this.svg.setAttribute('role', 'img');
    this.svg.setAttribute('aria-label', 'Calibration measurements and prediction intervals');
    canvas.hidden = true;
    canvas.parentElement.appendChild(this.svg);
    this.observer = new ResizeObserver(() => this.draw());
    this.observer.observe(canvas.parentElement);
    this.draw();
  }
  node(name, attributes, text) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', name);
    for (const [key, value] of Object.entries(attributes || {})) node.setAttribute(key, String(value));
    if (text !== undefined) node.textContent = String(text);
    this.svg.appendChild(node);
    return node;
  }
  draw() {
    this.svg.replaceChildren();
    const width = Math.max(320, this.canvas.parentElement.clientWidth || 800);
    const series = this.config.data.datasets;
    const perRow = Math.max(1, Math.floor(width / 210));
    const legendRows = Math.ceil(series.length / perRow);
    const top = 18 + legendRows * 22;
    const height = Math.max(340, this.canvas.parentElement.clientHeight || 380);
    const left = 112, right = width - 22, bottom = height - 52;
    this.svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    this.svg.style.cssText = 'display:block;width:100%;height:100%;min-height:340px';
    const options = this.config.options;
    const color = options.scales.x.ticks.color;
    const grid = options.scales.x.grid.color;
    series.forEach((dataset, index) => {
      const x = 8 + index % perRow * (width / perRow), y = 16 + Math.floor(index / perRow) * 22;
      this.node('rect', {x, y: y - 8, width: 9, height: 9, fill: dataset.borderColor || dataset.backgroundColor});
      const text = this.node('text', {x: x + 14, y, fill: color, 'font-size': 10,
        opacity: this.hidden.has(index) ? 0.4 : 1, role: 'button', tabindex: 0}, dataset.label);
      const toggle = () => {this.hidden.has(index) ? this.hidden.delete(index) : this.hidden.add(index); this.draw();};
      text.style.cursor = 'pointer';
      text.addEventListener('click', toggle);
      text.addEventListener('keydown', e => {if (e.key === 'Enter' || e.key === ' ') {e.preventDefault(); toggle();}});
    });
    const visible = series.map((dataset, index) => ({dataset, index})).filter(s => !this.hidden.has(s.index));
    const valid = point => point && typeof point.x === 'number' && Number.isFinite(point.x) && typeof point.y === 'number' && Number.isFinite(point.y);
    const points = visible.flatMap(s => s.dataset.data.filter(valid));
    if (!points.length) {this.node('text', {x: left, y: top + 40, fill: color}, 'No readings to plot'); return;}
    let xmin = Math.min(...points.map(p => p.x)), xmax = Math.max(...points.map(p => p.x));
    let ymin = Math.min(...points.map(p => p.y)), ymax = Math.max(...points.map(p => p.y));
    const xpad = (xmax - xmin) * 0.03 || 1;
    const ypad = (ymax - ymin) * 0.08 || Math.max(Math.abs(ymin) * 1e-6, 1e-9);
    xmin -= xpad; xmax += xpad; ymin -= ypad; ymax += ypad;
    const X = value => left + (value - xmin) / (xmax - xmin) * (right - left);
    const Y = value => bottom - (value - ymin) / (ymax - ymin) * (bottom - top);
    const label = value => Number(value.toPrecision(12)).toString();
    for (let i = 0; i <= 4; i++) {
      const xv = xmin + (xmax - xmin) * i / 4, yv = ymin + (ymax - ymin) * i / 4;
      this.node('line', {x1: X(xv), x2: X(xv), y1: top, y2: bottom, stroke: grid});
      this.node('line', {x1: left, x2: right, y1: Y(yv), y2: Y(yv), stroke: grid});
      this.node('text', {x: X(xv), y: bottom + 18, fill: color, 'text-anchor': 'middle', 'font-size': 10}, label(xv));
      this.node('text', {x: left - 8, y: Y(yv) + 3, fill: color, 'text-anchor': 'end', 'font-size': 10}, label(yv));
    }
    this.node('text', {x: (left + right) / 2, y: height - 8, fill: color, 'text-anchor': 'middle', 'font-size': 11}, options.scales.x.title.text);
    this.node('text', {x: left, y: top - 6, fill: color, 'font-size': 10}, options.scales.y.title.text);
    visible.sort((a, b) => (b.dataset.order || 0) - (a.dataset.order || 0)).forEach(({dataset, index}) => {
      if (dataset.fill === '+1' && !this.hidden.has(index + 1)) {
        const lower = series[index + 1]?.data || [];
        let segment = [];
        const flush = () => {
          if (segment.length > 1) {
            const upperPoints = segment.map(pair => `${X(pair[0].x)},${Y(pair[0].y)}`);
            const lowerPoints = segment.slice().reverse().map(pair => `${X(pair[1].x)},${Y(pair[1].y)}`);
            this.node('polygon', {points: upperPoints.concat(lowerPoints).join(' '), fill: dataset.backgroundColor, stroke: 'none'});
          }
          segment = [];
        };
        dataset.data.forEach((p, i) => {if (valid(p) && valid(lower[i])) segment.push([p, lower[i]]); else flush();});
        flush();
      }
      if (dataset.showLine) {
        let started = false;
        const path = dataset.data.map(point => {
          if (!valid(point)) {started = false; return '';}
          const command = started ? 'L' : 'M'; started = true;
          return `${command}${X(point.x)},${Y(point.y)}`;
        }).join(' ');
        this.node('path', {d: path, fill: 'none', stroke: dataset.borderColor,
          'stroke-width': dataset.borderWidth || 1, 'stroke-dasharray': (dataset.borderDash || []).join(' ')});
      }
      dataset.data.forEach((point, dataIndex) => {
        if (!valid(point) || dataset.pointRadius === 0) return;
        const x = X(point.x), y = Y(point.y), radius = dataset.pointRadius || 4;
        let marker;
        const attributes = {fill: dataset.backgroundColor || dataset.borderColor, stroke: dataset.borderColor || 'none', 'stroke-width': dataset.borderWidth || 0};
        if (dataset.pointStyle === 'rectRot') marker = this.node('polygon', {...attributes, points: `${x},${y-radius} ${x+radius},${y} ${x},${y+radius} ${x-radius},${y}`});
        else if (dataset.pointStyle === 'triangle') marker = this.node('polygon', {...attributes, points: `${x},${y-radius} ${x+radius},${y+radius} ${x-radius},${y+radius}`});
        else marker = this.node('circle', {...attributes, cx: x, cy: y, r: radius});
        const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        const callback = options.plugins.tooltip.callbacks.label;
        title.textContent = callback({raw: point, parsed: {y: point.y}, dataset, dataIndex}).join('\n');
        marker.appendChild(title);
      });
    });
  }
  destroy() {
    this.observer.disconnect();
    this.svg.remove();
    this.canvas.hidden = false;
  }
}
