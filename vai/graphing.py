from .common import inverse_lerp, lerp

# Scaling boundaries (assumes res between 1920x1080 and 3840x2160)
GRAPH_LABEL_FONT_SIZE_MIN = 5
GRAPH_LABEL_FONT_SIZE_MAX = 30

GRAPH_AXIS_LINE_WIDTH_MIN = 2
GRAPH_AXIS_LINE_WIDTH_MAX = 4

GRAPH_DATA_LINE_WIDTH_MIN = 2
GRAPH_DATA_LINE_WIDTH_MAX = 4

GRAPH_AXIS_TICK_LENGTH_MIN = 6
GRAPH_AXIS_TICK_LENGTH_MAX = 12

MAX_RES_WIDTH = 3840


def draw_graph_background_and_border(
    width,
    height,
    cr,
    bg_color=(0.1, 0.1, 0.1, 0.15),
    border_color=None,
    res_tuple=(1920, 1080),
):
    """
    Draws a background and border for the graph area. Can pass res to scale border reasonably

    Args:
        width: Width of the graph area
        height: Height of the graph area
        cr: Cairo context
        bg_color: Background color (RGBA tuple)
        border_color: Border color (RGBA tuple)
        res_tuple: Tuple of (width, height) of the screen resolution

    """
    line_width = int(
        lerp(
            GRAPH_AXIS_LINE_WIDTH_MIN,
            GRAPH_AXIS_LINE_WIDTH_MAX,
            res_tuple[0] / MAX_RES_WIDTH,
        )
    )
    cr.set_line_width(line_width)
    cr.set_source_rgba(*bg_color)

    # Offset by half the line width so the stroke is fully visible inside the widget:
    # In Cairo, rectangle(x, y, w, h) draws from (x, y) to (x + w, y + h).
    # The stroke is centered on the path, so we typically offset the path by line_width/2
    # and reduce the drawn rectangle dimensions accordingly.
    offset = line_width / 2.0

    cr.rectangle(
        offset,
        offset,
        width - line_width,
        height - line_width,
    )

    cr.fill_preserve()

    if border_color:
        cr.set_source_rgba(*border_color)
    cr.stroke()


def draw_axes_and_labels(
    cr,
    width,
    height,
    x_lim,
    y_lim,
    x_ticks=4,
    y_ticks=4,
    dynamic_margin=True,
    right_margin=20,
    bottom_margin=20,
    x_label=None,
    y_label=None,
    res_tuple=(1920, 1080),
):
    """
    Draws simple axes with labeled tick marks along bottom (x-axis) and left (y-axis).

    Args:
      cr      : Cairo context
      width   : total width of the drawing area
      height  : total height of the drawing area
      x_lim   : (xmin, xmax) for the data domain you want to label
      y_lim   : (ymin, ymax) for the data domain (like (0, 100))
      x_ticks : how many segments (thus x_ticks+1 labeled steps)
      y_ticks : how many segments (thus y_ticks+1 labeled steps)
      dynamic_margin: If True, the right and bottom margins will be scaled based on the resolution
      right_margin: Margin on the right side of the graph
      bottom_margin: Margin on the bottom of the graph
      x_label : Label for the x-axis
      y_label : Label for the y-axis
      res_tuple: Tuple of (width, height) of the screen resolution

    Returns:
        (x, y) axis positions
    """
    if not x_lim or not y_lim:
        return width, height

    if dynamic_margin:
        right_margin = lerp(20, 100, res_tuple[0] / MAX_RES_WIDTH)
        bottom_margin = lerp(20, 40, res_tuple[0] / MAX_RES_WIDTH)

    width -= right_margin  # Leave a little space on the right for the legend
    height -= bottom_margin  # Leave a little space on the bottom for the x-axis labels

    if not x_ticks or not y_ticks:  # No ticks, nothing to draw
        return width, height

    axis_width = lerp(
        GRAPH_AXIS_LINE_WIDTH_MIN,
        GRAPH_AXIS_LINE_WIDTH_MAX,
        res_tuple[0] / MAX_RES_WIDTH,
    )
    font_size = lerp(
        GRAPH_LABEL_FONT_SIZE_MIN,
        GRAPH_LABEL_FONT_SIZE_MAX,
        res_tuple[0] / MAX_RES_WIDTH,
    )

    cr.save()  # save the current transformation/state

    cr.set_line_width(axis_width)
    cr.set_source_rgb(1, 1, 1)  # white lines & text

    # --- Draw X-axis ---
    cr.move_to(0, height)
    cr.line_to(width, height)
    cr.stroke()

    # --- Draw Y-axis ---
    cr.move_to(width, 0)
    cr.line_to(width, height)
    cr.stroke()

    # Set font for labels
    cr.select_font_face("Sans", 0, 0)  # (slant=0 normal, weight=0 normal)
    cr.set_font_size(font_size)

    # --- X Ticks and Labels ---
    # e.g. if x_lim = (0,100), for 4 ticks => labeled at x=0,25,50,75,100
    x_min, x_max = x_lim
    dx = (x_max - x_min) / (x_ticks or 1)
    for i in range(x_ticks + 1):
        x_val = x_min + i * dx
        # Convert data → screen coordinate: 0..width
        x_screen = int((x_val - x_min) / ((x_max - x_min) or 1) * width)

        # Tick mark from (x_screen, height) up a bit
        tick_length = 6
        cr.move_to(x_screen, height)
        cr.line_to(x_screen, height - tick_length)
        cr.stroke()

        # Draw text label under the axis
        text = f"{int(x_val)}"
        te = cr.text_extents(text)
        text_x = x_screen - te.width // 2 if i != 0 else te.width // 2
        # At the intersection of the x/y axes, adjust text position further
        if i == x_ticks:
            text_x -= te.width
        text_y = height + te.height + 4
        cr.move_to(text_x, text_y)
        if i != 0:
            cr.show_text(text)
        elif x_label:
            cr.show_text(text + " " + x_label)

    # --- Y Ticks and Labels ---
    y_min, y_max = y_lim
    dy = (y_max - y_min) / (y_ticks or 1)
    for j in range(y_ticks + 1):
        y_val = y_min + j * dy
        y_ratio = (y_val - y_min) / ((y_max - y_min) or 1)
        y_screen = int(height - y_ratio * height)  # 0 -> bottom, height -> top

        tick_length = lerp(
            GRAPH_AXIS_TICK_LENGTH_MIN,
            GRAPH_AXIS_TICK_LENGTH_MAX,
            res_tuple[0] / MAX_RES_WIDTH,
        )
        cr.move_to(width, y_screen)
        cr.line_to(width - tick_length, y_screen)
        cr.stroke()

        text = f"{int(y_val)}"
        if y_label and j == y_ticks:
            text += y_label
        te = cr.text_extents(text)
        text_x = width + 4
        text_y = (
            y_screen + te.height // 2
            if j != y_ticks
            else y_screen + te.height + lerp(2, 4, res_tuple[0] / MAX_RES_WIDTH)
        )
        if j == 0:
            text_y -= te.height // 2
        cr.move_to(text_x, text_y)
        cr.show_text(text)

    cr.restore()
    return width, height


#def draw_graph_legend(label_color_map, width, cr, legend_x_width=None):
#    """
#    Draw the legend for the graph, returning the x position of the legend
#
#    Args:
#        label_color_map: Dict of label to RGB color tuple
#        width: Width of the graph area
#        cr: Cairo context
#        legend_x_width: Width of the legend box. If None, the width is determined by the labels
#    """
#    # --- Draw Legend ---
#    # TODO: Scale by res?
#    legend_margin_x = 20  # Distance from the right edge
#    legend_margin_y = 10  # Distance from the top edge
#    box_size = 20  # Size of the color box
#    spacing = 30  # Vertical spacing between entries
#    legend_padding_x = 5
#
#    cr.select_font_face("Sans", 0, 1)  # Bold weight & normal slant
#    cr.set_font_size(10)
#
#    text_guess_width = 11 * max(len(label) for label, _ in label_color_map.items())
#    legend_x = (
#        width - legend_x_width
#        if legend_x_width
#        else width - legend_margin_x - text_guess_width - box_size
#    )
#
#    # Tuning offset variable
#    for i, (label, color) in enumerate(label_color_map.items()):
#        item_y = legend_margin_y + i * spacing
#
#        # Draw color box
#        cr.set_source_rgb(*color)
#        cr.rectangle(legend_x, item_y, box_size, box_size)
#        cr.fill()
#
#        # Draw label text in white
#        cr.set_source_rgb(1, 1, 1)
#        text_x = legend_x + box_size + legend_padding_x
#        text_y = (
#            item_y + box_size - 5
#        )  # Shift text slightly so it's vertically centered
#        cr.move_to(text_x, text_y)
#        cr.show_text(label.upper())
#
#    return legend_x


def draw_graph_data(
    data_map,
    data_color_map,
    width,
    height,
    cr,
    y_lim=(0, 100),
    res_tuple=(1920, 1080),
):
    """Draw the graph data on the draw area with the given colors

    Args:
        data_map: Dict of data key to list of data values
        data_color_map: Dict of data key to RGB color tuple
        width: Width of the graph area
        height: Height of the graph area
        cr: Cairo context
        y_lim (optional): Tuple of min and max y values
    """
    if not data_map or not data_color_map:
        return

    graph_line_width = lerp(
        GRAPH_DATA_LINE_WIDTH_MIN,
        GRAPH_DATA_LINE_WIDTH_MAX,
        res_tuple[0] / MAX_RES_WIDTH,
    )
    cr.set_line_width(graph_line_width)

    for data_key, data in data_map.items():
        if data_key not in data_color_map:
            continue  # Skip if no color for this data (like timestamps)

        cr.set_source_rgb(*data_color_map[data_key])
        # Start the cursor at the first data point if possible
        # x is 0 or width because our data must always fit between 0 and width, (not the case for y values)
        cr.move_to(
            0 if data else width,
            (
                height
                if not data
                else int(lerp(0, height, 1 - inverse_lerp(y_lim[0], y_lim[1], data[0])))
            ),
        )
        # We must inverse lerp to get the % of the y value between the min and max y values for instances where y_lim is not 0-100
        for x in range(1, len(data)):
            y_pct = inverse_lerp(y_lim[0], y_lim[1], data[x])
            cr.line_to(
                int(
                    lerp(0, width, x / len(data))
                ),  # cant divide by 0 in this range definition
                int(lerp(0, height, 1 - y_pct)),
            )
        cr.stroke()
