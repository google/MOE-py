// Copyright 2010 Google Inc.
// All Rights Reserved

/**
 * @fileoverview MOE bootstrap script.
 *
 * @author nicksantos@google.com (Nick Santos)
 */

goog.provide('moe.dbapp');
goog.provide('moe.dbapp.Graph');

goog.require('goog.array');
goog.require('goog.dom');
goog.require('goog.events');
goog.require('goog.graphics');
goog.require('goog.ui.AnimatedZippy');
goog.require('moe.SaveArea');

/**
 * Bootstrap the current page.
 */
moe.dbapp.bootstrap = function() {
  moe.dbapp.decorateZippies();
  moe.dbapp.decorateSaveAreas();
  moe.dbapp.renderRecentHistory();
};


/**
 * Decorate the current page.
 */
moe.dbapp.decorateZippies = function() {
  goog.array.forEach(
      goog.dom.$$('div', 'goog-zippy'),
      function(el) {
        var header = goog.dom.getFirstElementChild(el);
        (new goog.ui.AnimatedZippy(
            header,
            goog.dom.getLastElementChild(el)));
        header.style.cursor = 'pointer';
      });
};


/**
 * Decorate the current page saving textareas.
 */
moe.dbapp.decorateSaveAreas = function() {
  goog.array.forEach(
      goog.dom.$$('div', 'moe-save-area'),
      function(el) {
        (new moe.SaveArea()).decorate(el);
      });
};


/**
 * Holds and renders a recent history DAG.
 *
 * This object uses //javascript/closure/graphics,
 * which provides cross-browser vector graphics via either SVG, Canvas, or VML.
 *
 * @param {number} width Width of the drawing surface.
 * @param {number} height Height of the drawing surface.
 * @constructor
 */
moe.dbapp.Graph = function(width, height) {
  this.gr_ = new goog.graphics.CanvasGraphics(200, height);
  this.gr_.createDom();
};

/**
 * Draws an equivalence between x0, y0, x1, and y1.
 *
 * @param {number} x0 X-coordinate of first point.
 * @param {number} y0 Y-coordinate of first point.
 * @param {number} x1 X-coordinate of second point.
 * @param {number} y1 Y-coordinate of second point.
 */
moe.dbapp.Graph.prototype.equivalence = function(x0, y0, x1, y1) {
  var path = this.gr_.createPath();
  path.moveTo(x0, y0);
  path.lineTo(x1, y1);
  var stroke = new goog.graphics.Stroke(1, 'green');
  this.gr_.drawPath(path, stroke, null);
};

/**
 * Draws an export between x0, y0, x1, and y1.
 *
 * @param {number} x0 X-coordinate of first point.
 * @param {number} y0 Y-coordinate of first point.
 * @param {number} x1 X-coordinate of second point.
 * @param {number} y1 Y-coordinate of second point.
 */
moe.dbapp.Graph.prototype.drawExport = function(x0, y0, x1, y1) {
  var path = this.gr_.createPath();
  path.moveTo(x0, y0 + 5); // exports go above equivalence line, for visibilty
  path.lineTo(x1, y1 + 5);
  var stroke = new goog.graphics.Stroke(1, 'blue');
  this.gr_.drawPath(path, stroke, null);
};

/**
 * Draws an import between x0, y0, x1, and y1.
 *
 * @param {number} x0 X-coordinate of first point.
 * @param {number} y0 Y-coordinate of first point.
 * @param {number} x1 X-coordinate of second point.
 * @param {number} y1 Y-coordinate of second point.
 */
moe.dbapp.Graph.prototype.drawImport = function(x0, y0, x1, y1) {
  var path = this.gr_.createPath();
  path.moveTo(x0, y0 - 5); // imports go below equivalence line, for visibilty
  path.lineTo(x1, y1 - 5);
  var stroke = new goog.graphics.Stroke(1, 'red');
  this.gr_.drawPath(path, stroke, null);
};

/**
 * Draws a revision at x, y.
 *
 * @param {number} x X-coordinate of first point.
 * @param {number} y Y-coordinate of first point.
 */
moe.dbapp.Graph.prototype.vertex = function(x, y) {
  var stroke = new goog.graphics.Stroke(1, 'black');
  var fill = new goog.graphics.SolidFill('#c3d9ff');
  this.gr_.drawCircle(x, y, 4, stroke, fill);
};

/**
 * Draws the graph inside the given element.
 *
 * @param {Element} dest Destination element in which to create
 *   the graphics element.
 * @param {Object} recentHistory The recent history to display.
 * @param {number} xIncr The distance in pixels between two columns.
 * @param {number} yIncr The distance in pixels between two rows.
 */
moe.dbapp.Graph.prototype.render = function(dest, recentHistory, xIncr, yIncr) {
  var xOffset = 10;
  var yOffset = yIncr / 2;
  var internalRevisions = recentHistory['internal_revisions'];
  var internalRowById = {};
  for (var i = 0; i < internalRevisions.length; i++) {
    var r = internalRevisions[i];
    internalRowById[r['rev_id']] = i;
    this.vertex(xOffset, yOffset + i * yIncr);
  }

  var publicRevisions = recentHistory['public_revisions'];
  var publicRowById = {};
  for (var i = 0; i < publicRevisions.length; i++) {
    var r = publicRevisions[i];
    publicRowById[r['rev_id']] = i;
    this.vertex(xOffset + xIncr, yOffset + i * yIncr);
  }

  var equivalences = recentHistory['equivalences'];
  for (var i = 0; i < equivalences.length; i++) {
    var e = equivalences[i];
    var internalRow = internalRowById[e['internal_revision']['rev_id']];
    var publicRow = publicRowById[e['public_revision']['rev_id']];
    if (internalRow && publicRow) {
      this.equivalence(
          xOffset, yOffset + internalRow * yIncr,
          xOffset + xIncr, yOffset + publicRow * yIncr
          );
    }
  }

  var exports = recentHistory['exports'];
  for (var i = 0; i < exports.length; i++) {
    var m = exports[i];
    var internalRow = internalRowById[m['up_to_revision']['rev_id']];
    var publicRow = publicRowById[m['submitted_as']['rev_id']];
    if (internalRow && publicRow) {
      this.drawExport(
          xOffset, yOffset + internalRow * yIncr,
          xOffset + xIncr, yOffset + publicRow * yIncr
          );
    }
  }

  var imports = recentHistory['imports'];
  for (var i = 0; i < imports.length; i++) {
    var m = imports[i];
    var internalRow = internalRowById[m['submitted_as']['rev_id']];
    var publicRow = publicRowById[m['up_to_revision']['rev_id']];
    if (internalRow && publicRow) {
      this.drawImport(
          xOffset, yOffset + internalRow * yIncr,
          xOffset + xIncr, yOffset + publicRow * yIncr
          );
    }

  }

  this.gr_.render(dest);
  dest.className = 'moe-graph';
};

/**
 * Renders the recent history onto the page.
 */
moe.dbapp.renderRecentHistory = function() {
  if (typeof recentHistory == 'undefined') {
    return;
  }

  var internal_revisions = recentHistory['internal_revisions'];
  var public_revisions = recentHistory['public_revisions'];

  var num_rows = Math.max(
      internal_revisions.length,
      public_revisions.length
      );

  var table = goog.dom.createTable(0, 3);
  var row = table.insertRow(0);
  var cell = row.insertCell(-1);
  goog.dom.setTextContent(cell, 'Internal');
  cell = row.insertCell(-1);
  cell.innerHTML = "<div style='width: 120px;'>&nbsp;</div>";
  cell = row.insertCell(-1);
  goog.dom.setTextContent(cell, 'Public');

  // We first set the content so that the browser can tell us offsetHeight.
  // This is... maybe?... the right thing to do.

  for (var i = 0; i < num_rows; i++) {
    row = table.insertRow(i + 1);
    var internalCell = row.insertCell(-1);
    var r = internal_revisions[i];
    internalCell.className = 'moe-recent-history-internal-cell';
    if (r) {
      goog.dom.setTextContent(internalCell, r['rev_id']);
    }
    var graphCell = row.insertCell(-1);
    graphCell.className = 'moe-recent-history-cell';
    var publicCell = row.insertCell(-1);
    r = public_revisions[i];
    if (r) {
      goog.dom.setTextContent(publicCell, r['rev_id']);
    }
  }

  var target = goog.dom.getElement('recent-history');
  table.className = 'moe-recent-history-table';
  goog.dom.appendChild(target, table);

  var xIncr = 100;
  var width = 400;
  var height = (table.rows.length - 1) * (table.rows[0].offsetHeight + 2);
  var yIncr = height / (table.rows.length - 1);

  var destElement = table.rows[1].cells[1];
  var gr = new moe.dbapp.Graph(width, height);
  gr.render(destElement, recentHistory, xIncr, yIncr);
};

goog.events.listen(window, 'load', moe.dbapp.bootstrap);
