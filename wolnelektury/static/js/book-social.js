$(function() {


function text_len(elem) {
    switch (elem.nodeType) {
        case 1:  // element
            var $elem = $(elem);
            if ($elem.hasClass('tlen0'))
                return 0;
            var tlen = parseInt($elem.attr('data-tlen'));
            if (isNaN(tlen)) {
                tlen = 0;
                $elem.contents().each(function(i, e) {tlen += text_len(e);});
                $elem.attr('data-tlen', tlen);
            }
            return tlen;
        case 3:  // text
            return elem.data.length;
        case 8:  // comment
            return 0;
        default:
            alert("unknown type " + elem.nodeType);
    }
}


function text_offset(elem) {
    var $elem = $(elem);
    if ($elem.attr('id') == 'book-text') return 0;
    var $parent = $elem.parent();
    if (!$parent.length) {
        return NaN;
    }
    var $prev = $($elem.get(0).previousSibling);
    if ($prev.length) {
        return text_len($prev.get(0)) + text_offset($prev);
    }
    else {
        return text_offset($parent);
    }
}


var citeBox = function() {
    var $cite_box = $("#cite-box");
    var $uform = $("#underline-form", $cite_box);
    var $uform_start = $("#id_start", $uform);
    var $uform_end = $("#id_end", $uform);
    var $cform = $("#underline-comment-form", $cite_box);
    var $cform_comment = $("#id_comment", $cform);
    var $text = $("#text", $cite_box);

    return function(opts) {
        if (opts.hide) {
            $cite_box.hide();
            return;
        }

        var time_hide = 0;
        var time_show = 0;
        if (opts.top) {
            $cite_box.get(0).style.top = opts.top + "px";
            $text.html("");
        }
        else {
            var time_hide = 300;
            var time_show = 500;
        }

        $uform_start.attr("value", opts.start);
        $uform_end.attr("value", opts.start);
        if (opts.text !== undefined)
            $text.html("<pre>«" + opts.text + "»</pre>");

        $cite_box.show();

        if (opts.comment) {
            $uform.hide(time_hide, function() {
                $cform.show(time_show);
            });
        }
        else {
            $cform.hide(time_hide, function() {
                $uform.show(time_show);
            });
        }

        $cite_box.show();
        //reselect the selection here
    };
}();


var markSelection = (function() {
    var markerTextChar = "\ufeff";
    var markerTextCharEntity = "&#xfeff;";

    var markerEl, markerId = "sel_" + new Date().getTime() + "_" + Math.random().toString().substr(2);

    return function(e) {
        // don't do anything in a box!
        var node=e.target;
        while (node && !$(node).hasClass('ignore')) {
            node = node.parentNode;
        }
        if (node) return;

        var sel, range;

        if (document.selection && document.selection.createRange) {
            // Clone the TextRange and collapse
            range = document.selection.createRange().duplicate();
            range.collapse(false);

            // Create the marker element containing a single invisible character by creating literal HTML and insert it
            range.pasteHTML('<span id="' + markerId + '" style="position: relative;">' + markerTextCharEntity + '</span>');
            markerEl = document.getElementById(markerId);
        } else if (window.getSelection) {
            sel = window.getSelection();

            if (sel.getRangeAt) {
                range = sel.getRangeAt(0).cloneRange();
            } else {
                // Older WebKit doesn't have getRangeAt
                range.setStart(sel.anchorNode, sel.anchorOffset);
                range.setEnd(sel.focusNode, sel.focusOffset);

                // Handle the case when the selection was selected backwards (from the end to the start in the
                // document)
                if (range.collapsed !== sel.isCollapsed) {
                    range.setStart(sel.focusNode, sel.focusOffset);
                    range.setEnd(sel.anchorNode, sel.anchorOffset);
                }
            }
            var r = sel.getRangeAt(0);
            // remember the text
            var text = "" + r;

            var soff = text_offset(r.startContainer) + r.startOffset;
            var eoff = text_offset(r.endContainer) + r.endOffset;

            if (soff == eoff) {
                citeBox({hide: true});
                return;
            }

            //if (eoff < soff)
                range.collapse(true);
            //else
                //range.collapse(false);

            // Create the marker element containing a single invisible character using DOM methods and insert it
            markerEl = document.createElement("span");
            markerEl.id = markerId;
            markerEl.appendChild( document.createTextNode(markerTextChar) );
            range.insertNode(markerEl);
        }

        if (markerEl) {

            // Find markerEl position http://www.quirksmode.org/js/findpos.html
            var obj = markerEl;
            var top = 0;
            do {
                top += obj.offsetTop;
            } while (obj = obj.offsetParent);

            citeBox({
                start: soff,
                end: eoff,
                top: top,
                text: text
            });

            markerEl.parentNode.removeChild(markerEl);
        }
    };
})();


function offset_to_pair(offset, $cursor) {
    if ($cursor === undefined) {
        $cursor = $("#book-text");
    }

    if (!$cursor.length) {
        return [undefined, undefined];
    }
    var tl = text_len($cursor.get(0));
    if (tl < offset)
        return offset_to_pair(offset - tl, $($cursor.get(0).nextSibling))
    if ($cursor.contents().length)
        return offset_to_pair(offset, $($cursor.contents().get(0)))
    return [$cursor.get(0), offset]
}


$(document).bind("mouseup", markSelection);

  if (location.hash) {
    var selection = window.getSelection();
    selection.removeAllRanges();
    var range = document.createRange();

    //var e = $(".theme-end[fid='" + $(this).attr('fid') + "']")[0];

    //if (e) {
        range.setStartAfter(this);
        range.setEndBefore(e);
        selection.addRange(range);
    //}
  }


    function add_underline_marker(start_offset, end_offset, comment) {
        var range = document.createRange(); // rangy.createRange()
        var point = offset_to_pair(start_offset);
        if (!point[0]) {return;}
        range.setStart(point[0], point[1]);
        range.setEnd(point[0], point[1]);
        var $marker = $("<span class='tlen0 underline-marker' style='float:right'>!</span>");
        $marker.attr('data-start', start_offset);
        $marker.attr('data-end', end_offset);
        $marker.attr('title', comment);
        range.insertNode($marker.get(0));
    }


    // FIXME: there should be one class for decoration
    $(".anchor").attr("data-tlen", 0);
    $(".theme-begin").attr("data-tlen", 0);


    $(".underline").each(function(i, e) {
        $this = $(this);
        add_underline_marker($this.attr('data-start'), $this.attr('data-end'),
            $this.attr('data-comment'));
    });


    $(".underline-marker").live("click", function() {
        $this = $(this);
        var range = document.createRange(); // rangy.createRange() if not using Rangy
        var point = offset_to_pair($this.attr('data-start'));
        range.setStart(point[0], point[1]);
        var point = offset_to_pair($this.attr('data-end'));
        range.setEnd(point[0], point[1]);
        var selection = window.getSelection();

        selection.addRange(range);
    });


    $('#underline-form').ajaxForm({
        success: function(response, ) {
            alert(response);
            var form = $('#underline-form').get(0);
            add_underline_marker(form.start.value, form.end.value);
            citeBox({comment: true});
            }
    });


});
