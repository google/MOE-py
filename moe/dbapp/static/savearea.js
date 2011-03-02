// Copyright 2011 Google Inc.
// All Rights Reserved

/**
 * @fileoverview A UI widget that attaches to a form with
 * a textarea, and turns the form POST into an XHR POST.
 *
 * @author nicksantos@google.com (Nick Santos)
 */

goog.provide('moe.SaveArea');

goog.require('goog.Uri');
goog.require('goog.net.XhrIo');
goog.require('goog.ui.Component');


/**
 * A UI widget that attaches to a form with
 * a textarea, and turns the form POST into an XHR PORT.
 *
 * @constructor
 * @extends {goog.ui.Component}
 */
moe.SaveArea = function() {
  goog.base(this);
};
goog.inherits(moe.SaveArea, goog.ui.Component);


/**
 * @type {Element}
 * @private
 */
moe.SaveArea.prototype.feedbackEl_;

/**
 * @type {Element}
 * @private
 */
moe.SaveArea.prototype.saveButtonEl_;

/** @override */
moe.SaveArea.prototype.decorateInternal = function(el) {
  goog.base(this, 'decorateInternal', el);

  this.feedbackEl_ = goog.dom.getElementsByTagNameAndClass(
      '*', 'moe-save-area-feedback', this.getElement())[0];

  var previousSib = this.feedbackEl_.previousSibling;
  if (!previousSib || previousSib.tagName != 'BUTTON') {
    goog.dom.insertSiblingBefore(
        goog.dom.createDom('input', {'type': 'button', 'value': 'Save'}),
        this.feedbackEl_);
  }
  this.saveButtonEl_ = this.feedbackEl_.previousSibling;
};



/** @override */
moe.SaveArea.prototype.enterDocument = function() {
  this.getHandler().listen(
      this.saveButtonEl_,
      'click',
      this.handleSave_);
};


/**
 * @param {boolean} enable
 * @private
 */
moe.SaveArea.prototype.setButtonsEnabled_ = function(enable) {
  var buttons = goog.dom.getElementsByTagNameAndClass(
      'input', null, this.getElement());
  for (var i = 0; i < buttons.length; i++) {
    var type = buttons[i].type;
    if (type == 'submit' || type == 'button') {
      buttons[i].disabled = !enable;
    }
  }
};


/**
 * @param {goog.events.BrowserEvent} e
 * @private
 */
moe.SaveArea.prototype.handleSave_ = function(e) {
  // Find the URL that we want to post on.
  var root = this.getElement();
  var postUrl = new goog.Uri(root.getAttribute('action'));

  // Add the edited text to the POST content.
  var postContent = [];
  var elements = goog.dom.getElementsByTagNameAndClass(
      '*', null, root);
  for (var i = 0; i < elements.length; i++) {
    var el = elements[i];
    if (el.name) {
      // strip off any indices.
      var name = el.name.replace(/_[0-9]+$/, '');
      postContent.push(
          encodeURIComponent(name) + '=' +
          encodeURIComponent(el.value));
    }
  }

  // While we're waiting, disable the save button.
  this.setButtonsEnabled_(false);
  this.setFeedback_('');

  // Send it.
  goog.net.XhrIo.send(
      postUrl,
      goog.bind(this.handlePostComplete_, this),
      'POST',
      postContent.join('&'));
};


/**
 * @param {string} msg
 */
moe.SaveArea.prototype.setFeedback_ = function(msg) {
  goog.dom.setTextContent(this.feedbackEl_, msg);
};


/**
 * @param {goog.events.Event} e
 * @private
 */
moe.SaveArea.prototype.handlePostComplete_ = function(e) {
  this.setButtonsEnabled_(true);

  if (e.target.isSuccess()) {
    this.setFeedback_(
        'Last saved at: ' + (new Date()).toTimeString());
  } else {
    this.setFeedback_(
        'Error: ' + e.target.getLastError());
  }
};
