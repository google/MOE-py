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


/** @override */
moe.SaveArea.prototype.enterDocument = function() {
  this.getHandler().listen(
      this.getElement(),
      'submit',
      this.handleFormSubmit_);
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
moe.SaveArea.prototype.handleFormSubmit_ = function(e) {
  e.preventDefault();

  var root = this.getElement();

  // Find the URL that we want to post on. Modify this URL so that the server
  // returns the results as JSON instead of an HTML page.
  var form = goog.dom.getElementsByTagNameAndClass(
      'form', null, root)[0];
  var postUrl = new goog.Uri(form.action);
  postUrl.removeParameter('out');

  // Add the edited text to the POST content.
  var postContent = [];
  var elements = goog.dom.getElementsByTagNameAndClass(
      '*', null, root);
  for (var i = 0; i < elements.length; i++) {
    var el = elements[i];
    if (el.name) {
      postContent.push(
          encodeURIComponent(el.name) + '=' +
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
  var feedback = goog.dom.getElementsByTagNameAndClass(
      '*', 'moe-save-area-feedback', this.getElement())[0];
  goog.dom.setTextContent(feedback, msg);
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
