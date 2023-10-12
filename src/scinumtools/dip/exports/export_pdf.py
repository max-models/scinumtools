from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.rl_config import defaultPageSize
from reportlab.lib.units import inch
import numpy as np

from ..environment import Environment
from ..settings import Order, Sign, Keyword
from ..lists import NodeList
from ..nodes import Node, BooleanNode, IntegerNode, FloatNode, StringNode

class ExportPDF:
    
    env: Environment
    
    def __enter__(self):
        return self
    
    def __exit__(self, type, value, traceback):
        pass
    
    def __init__(self, env: Environment, **kwargs):
        self.env = env
        
    def export(self, file_path: str):
        
        PAGE_HEIGHT=defaultPageSize[1]; PAGE_WIDTH=defaultPageSize[0]
        styles = getSampleStyleSheet()
        title = "DIP Documentation"
        pageinfo = "DIP Documentation"
        fontName = 'Helvetica'
        fontSize = 10
        
        groupStyle = ParagraphStyle(
            "CustomStyle",
            parent=styles["Normal"],
            fontName=fontName,
            fontSize=12,
            spaceBefore=0, 
            spaceAfter=10,  # Add 20 points of space after the paragraph
        )
        tableHeaderStyle = ParagraphStyle(
            "CustomStyle",
            parent=styles["Normal"],
            fontName=fontName,
            fontSize=fontSize,
            textColor=colors.saddlebrown
        )
        tableBodyStyle = ParagraphStyle(
            "CustomStyle",
            parent=styles["Normal"],
            fontName=fontName,
            fontSize=fontSize,
        )
        tableStyle = [
            # whole grid
            ('GRID',       (0,0), (-1,-1),  0.5,     colors.goldenrod),
            ('FONTNAME',   (0,0), (-1,-1),  tableBodyStyle.fontName),
            ('FONTSIZE',   (0,0), (-1,-1),  tableBodyStyle.fontSize),
            # top panel
            ('FONTSIZE',   (0,0), (-1,-1),  tableHeaderStyle.fontSize),
            ('TEXTCOLOR',  (1,0), (-1,0),   colors.saddlebrown),   
            ('BACKGROUND', (1,0), (-1,0),   colors.navajowhite),   
            # left case strip
            ('SPAN',       (0,0), (0,-1)    ),                              
            ('BACKGROUND', (0,0), (0,-1),   colors.navajowhite),
            # property names
            ('BACKGROUND', (1,1), (1,-1),   colors.antiquewhite),  
            # property values
            ('BACKGROUND', (2,1), (-1,-1),  colors.floralwhite),   
            # parameter name
            ('SPAN',       (1,0), (2,0)     ),                               
        ]

        doc = SimpleDocTemplate(file_path)
        blocks = [Spacer(1,1*inch)]
        
        def myFirstPage(canvas, doc):
            canvas.saveState()
            canvas.setFont('Times-Bold',16)
            canvas.drawCentredString(PAGE_WIDTH/2.0, PAGE_HEIGHT-108, title)
            canvas.setFont('Times-Roman',9)
            canvas.drawString(inch, 0.75 * inch, "First Page / %s" % pageinfo)
            canvas.restoreState()
            
        def myLaterPages(canvas, doc):
            canvas.saveState()
            canvas.setFont('Times-Roman',9)
            canvas.drawString(inch, 0.75 * inch, "Page %d %s" % (doc.page, pageinfo))
            canvas.restoreState()

        def prepare_values(node):
            unit = ''
            if node.value and node.value.unit:
                unit = node.value.unit
            elif node.units_raw:
                unit = node.units_raw
            value = None
            if node.keyword == IntegerNode.keyword:
                dtype = node.keyword
                if node.value:
                    value = str(int(node.value.value))
                    if node.value.unsigned:
                        dtype = f"u{dtype}"
                    if node.value.precision:
                        dtype = f"{dtype}{node.value.precision}"
            elif node.keyword == FloatNode.keyword:
                dtype = node.keyword
                if node.value:
                    exp = np.log10(node.value.value)
                    if exp<=3 or exp>=-3:
                        value = f"{node.value.value:.03f}"
                    else:
                        value = f"{node.value.value:.03e}"
                    if node.value.precision:
                        dtype = f"{dtype}{node.value.precision}"
            elif node.keyword == BooleanNode.keyword:
                dtype = node.keyword
                if node.value:
                    value = Keyword.TRUE if node.value.value else Keyword.FALSE
            elif node.keyword == StringNode.keyword:
                dtype = node.keyword
                if node.value:
                    value = str(node.value.value)
                
            return dtype, value, unit
        
        def print_node(node, parent_name:str=''):
            name = f"<strong>{node.name}</strong>"
            const = "const" if node.constant else ""
            p = Paragraph(name, tableHeaderStyle)
            dtype, value, unit = prepare_values(node)
            data = [
                ['', p, '', dtype, unit, const],
            ]
            tableStyle2 = tableStyle.copy()
            if value:
                tableStyle2.append(('SPAN', (2,len(data)), (-1,len(data)) ))
                data.append(['','Default value:', Paragraph(value, tableBodyStyle), '', '',''])
            if node.condition:
                condition = node.condition
                condition = condition.replace("{","<font color='orange'>{")
                condition = condition.replace("}","}</font>")
                #print(condition)
                condition = Paragraph(condition, style=tableBodyStyle)
                tableStyle2.append(('SPAN', (2,len(data)), (-1,len(data)) ))
                data.append(['','Condition:', condition, '', '', ''])
            if node.tags:
                tableStyle2.append(('SPAN', (2,len(data)), (-1,len(data)) ))
                data.append(['', 'Tags:', Paragraph(", ".join(node.tags), tableBodyStyle), '', '', ''])
            if node.keyword != BooleanNode.keyword and node.options:
                options = [str(option.value.value) for option in node.options]
                tableStyle2.append(('SPAN', (2,len(data)), (-1,len(data)) ))
                data.append(['', 'Options:', Paragraph(", ".join(options), tableBodyStyle), '', '', ''])
            if node.keyword == StringNode.keyword and node.format:
                tableStyle2.append(('SPAN', (2,len(data)), (-1,len(data)) ))
                data.append(['', 'Format:', Paragraph(node.format, tableBodyStyle), '', '', ''])
            if node.description:
                tableStyle2.append(('SPAN', (1,-1), (-1,-1) ))
                tableStyle2.append(('BACKGROUND', (1,-1), (-1,-1),  colors.floralwhite))
                data.append(['', Paragraph(node.description, tableBodyStyle), '', '', '', ''])
            colWidths = list(np.array([0.01, 0.19, 0.2, 0.12, 0.38, 0.1])*(PAGE_WIDTH-2*inch))
            t = Table(data,style=tableStyle2, hAlign='LEFT', colWidths=colWidths)
            return t

        def collect_blocks(nodes, parent_name:str=''):
            blocks = []
            for group_name in nodes.keys():
                if parent_name:
                    group_path = f"{parent_name}{Sign.SEPARATOR}{group_name}"
                else:
                    group_path = group_name
                child = nodes[group_name]
                if isinstance(child, NodeList) and len(child):
                    blocks += collect_blocks(child, group_path)
                elif isinstance(child, Node):
                    blocks.append(print_node(child, parent_name))
                    blocks.append(Spacer(inch, inch/12))
                #blocks.append(Spacer(1,0.2*inch))
            if blocks:
                p = Paragraph(f"<strong>{parent_name}</strong>", groupStyle)
                blocks.insert(0, p)
            return blocks
            
        for block in collect_blocks(self.env.nodes):
            blocks.append(block)
            
        doc.build(blocks, onFirstPage=myFirstPage, onLaterPages=myLaterPages)    
