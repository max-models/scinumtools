import numpy as np
import re
import os
from pathlib import Path
from typing import List, Callable, Tuple
from inspect import getframeinfo, stack

from .environment import Environment
from .source import Source
from .settings import Keyword, Sign, EnvType
from .nodes.parser import Parser
from .nodes import EmptyNode, ImportNode, UnitNode, SourceNode, CaseNode
from .nodes import OptionNode, ConstantNode, FormatNode, ConditionNode, TagsNode, DescriptionNode
from .nodes import ModNode, GroupNode
from .nodes import BooleanNode, IntegerNode, FloatNode, StringNode, TableNode
from .solvers import LogicalSolver
from .datatypes import Type

class DIP:
    """ DIP parser class

    :param str code: DIP code
    :param DIP_Environment env: DIP environment object
    """
    env: Environment
    lines: List[dict]
    source: Source
    
    nodes_special: list     = ['empty','unit','source']
    nodes_properties: list  = ['option','constant','format','condition','tags','description']
    nodes_hierarchy: list   = ['group']
    nodes_nohierarchy: list = None
    nodes_notypes: list     = None

    def __init__(self, env:Environment=None, **kwargs):
        self.lines = []
        # create a new environment if not givenl
        if env:
            self.env = env
        elif 'env' not in kwargs:
            self.env = Environment()
        else:
            self.env = None
        # find out source
        if 'source' not in kwargs:
            # determine which file instantiate this class
            caller = getframeinfo(stack()[1][0])
            if caller.filename == '<stdin>':                
                self.source = Source(lineno=caller.lineno, filename=os.getcwd())
            else:
                self.source = Source(lineno=caller.lineno, filename=caller.filename)
        else:
            self.source = kwargs['source']
        # create additional node groups
        self.nodes_nohierarchy = self.nodes_special+self.nodes_properties
        self.nodes_notypes = self.nodes_special+self.nodes_properties+self.nodes_hierarchy

    def __enter__(self):
        return self
    
    def __exit__(self, type, value, traceback):
        pass
        
    def _get_queue(self):
        # Convert code lines to nodes
        queue = Environment()
        while len(self.lines)>0:
            line = self.lines.pop(0)
            # Group block structures
            if '"""' in line['code']:
                block = []
                while len(self.lines)>0:
                    subline = self.lines.pop(0)
                    if '"""' in subline['code']:
                        line['code'] += Sign.NEWLINE.join(block) + subline['code'].lstrip()
                        break
                    else:
                        block.append( subline['code'] )
                else:
                    raise Exception("Block structure is not properly terminated.", line['code'])
            node = self._determine_node(line)
            queue.nodes.append(node)
        return queue

    def _determine_node(self, line):
        # Add replacement marks
        # TODO: we need to also properly treate arrays like this ["d#", "b"]
        encode = ["\\'", '\\"', "\n"]
        for i,symbol in enumerate(encode):
            line['code'] = line['code'].replace(symbol,f"$@{i:02d}")
            
        # Determine node type
        parser = Parser(
            code=line['code'],
            source=line['source']
        )
        steps = [
            EmptyNode.is_node,            # parse empty line node
            parser.part_indent,           
            ImportNode.is_node,           # parse root import directive
            UnitNode.is_node,             # parse unit directive
            SourceNode.is_node,           # parse source directive
            CaseNode.is_node,             # parse case directive
            OptionNode.is_node,           # parse option setting
            ConstantNode.is_node,         # parse constant setting
            FormatNode.is_node,           # parse format setting
            TagsNode.is_node,             # parse node tags
            DescriptionNode.is_node,      # parse description node
            ConditionNode.is_node,        # parse condition setting
            parser.part_name,             
            GroupNode.is_node,            # parse group node
            ImportNode.is_node,           # parse group import directive
            ModNode.is_node,              # parse modification
            parser.part_type,             
            BooleanNode.is_node,          # parse boolean node
            IntegerNode.is_node,          # parse integer node
            FloatNode.is_node,            # parse float node
            StringNode.is_node,           # parse string node
            TableNode.is_node,            # parse table node
        ]
        node = None
        for step in steps:
            if step.__name__=='is_node':
                node = step(parser)
                if node:
                    node = node
            else:
                step()
            if node and parser.is_empty():
                break
        else:
            raise Exception(f"Code cannot be parsed:",parser.ccode)
        
        # Convert symbols to original letters
        def decode_symbols(value):
            replace = ["\'", '\"', "\n"]
            if isinstance(value, (list, np.ndarray)):
                value = [decode_symbols(v) for v in value]
            elif value is None:
                return value
            else:
                for i,symbol in enumerate(replace):
                    value = value.replace(f"$@{i:02d}", symbol)
            return value
        
        # Remove replacement marks
        if node.value_fn:
            node.value_fn = decode_symbols(node.value_fn)
        if node.value_expr:
            node.value_expr = decode_symbols(node.value_expr)
        node.value_raw = decode_symbols(node.value_raw)
        node.code = decode_symbols(node.code)

        # Return proper node type
        return node
    
    def from_file(self, filepath:str):
        """ Load DIP code from a file

        :param str filepath: Path to a DIP file
        """
        if not os.path.isabs(filepath):
            # set relative paths with respect to the source script
            parent = Path(self.source.filename)
            if os.path.isfile(parent):
                filepath = parent.parent / filepath
            else:
                filepath = parent / filepath
        with open(filepath,'r') as f:           
            lines = f.read().split(Sign.NEWLINE)
        for line,code in enumerate(lines):
            self.lines.append(dict(
                code = code,
                source = Source(
                    lineno=line+1,
                    filename=os.path.realpath(filepath),
                    primary=self.source.primary
                )
            ))
        
    def from_string(self, code:str):
        """ Use DIP code from a string

        :param str code: DIP code
        """
        lines = code.split(Sign.NEWLINE)
        for line,code in enumerate(lines):
            self.lines.append(dict(
                code = code,
                source = self.source,
            ))

    def add_source(self, name:str, path:str):
        self.lines.append(dict(
            code = f"{Sign.VARIABLE}{Keyword.SOURCE} {name} = {path}",
            source = self.source
        ))
        
    def add_unit(self, name:str, value:float, unit:str=None):
        if unit:
            code = f"{Sign.VARIABLE}{Keyword.UNIT} {name} = {value} {unit}"
        else:
            code = f"{Sign.VARIABLE}{Keyword.UNIT} {name} = {value}"
        self.lines.append(dict(
            code = code,
            source = self.source
        ))

    def add_function(self, name:str, fn:Callable):
        self.env.functions.append(name, fn)

    def parse(self):
        """ Parse DIP nodes from code lines
        """
        # Create queue/target environment
        queue = self._get_queue()
        target = self.env.copy()
        # Parse nodes
        while len(queue.nodes):
            node = queue.nodes.pop()
            # Perform specific node parsing only outside of case or inside of valid case
            if not target.branching.false_case() or node.keyword=='case':
                node.inject_value(target)
                parsed = node.parse(target)
                if parsed: 
                    # Add parsed nodes to the queue and continue
                    queue.nodes.prepend(parsed)
                    continue
            # Create hierarchical name
            target.hierarchy.register(node, self.nodes_nohierarchy)
            # Add nodes to the node list
            if node.keyword in self.nodes_notypes:
                continue
            elif node.keyword=='case':   # Parse cases
                target.branching.solve_case(node)
            elif target.branching.false_case():
                continue
            else:
                target.branching.prepare_node(node)
                # Clean node name from cases
                node.name = node.clean_name()
                # Set the node value
                node.set_value()
                # If node was previously defined, modify its value
                for n in range(len(target.nodes)):
                    if target.nodes[n].name==node.name:
                        if target.nodes[n].constant:
                            raise Exception(f"Node '{target.nodes[n].name}' is constant and cannot be modified:",node.code)
                        target.nodes[n].modify_value(node, target)
                        break
                # If node wasn't defined, create a new node
                else:
                    if node.keyword=='mod' and node.source.primary:
                        raise Exception(f"Modifying undefined node:",node.name)
                    target.nodes.append(node)
        # Validate nodes
        for node in target.nodes:
            # Check if all declared nodes have assigned value
            if node.defined and node.value is None:
                raise Exception(f"Node value must be defined:", node.code)
            # Check if node value is in options
            if isinstance(node,(IntegerNode, FloatNode, StringNode)):
                node.validate_options()
            # Check conditions
            if node.keyword in ['float','int'] and node.condition:
                target.autoref = node.name
                with LogicalSolver(target) as s:
                    if not s.solve(node.condition).value:
                        raise Exception("Node does not fullfil a condition:",
                                        node.name, node.condition)
                target.autoref = None
            # Check formats if set for strings
            if node.keyword=='str' and node.format:
                m = re.match(node.format, node.value.value)
                if not m:
                    raise Exception("Node value does not match the format:",
                                    node.value.value, node.format)
        return target
        
    def parse_docs(self):
        """ Parse DIP node definitions for a documentation
        """
        # Create queue/target environment
        queue = self._get_queue()
        target = self.env.copy()
        target.envtype = EnvType.DOCS
        # Parse nodes
        while len(queue.nodes):
            node = queue.nodes.pop()
            # Perform specific node parsing
            node.inject_value(target)
            parsed = node.parse(target)
            if parsed: 
                # Add parsed nodes to the queue and continue
                queue.nodes.prepend(parsed)
                continue
            # Create hierarchical name
            target.hierarchy.register(node, self.nodes_nohierarchy)
            # Add nodes to the node list
            if node.keyword in self.nodes_notypes:
                continue
            elif node.keyword=='case':   # Parse cases
                target.branching.solve_case(node)
            else:
                target.branching.prepare_node(node)
                # Set the node value
                node.set_value()
                # Loop through all nodes and find modifications
                for n in range(len(target.nodes)):
                    # Continue if names do not match
                    target_name = target.nodes[n].clean_name()
                    target_branch_id = target.nodes[n].branch_id
                    if target_name != node.clean_name():
                        continue  # nodes have different names
                    if target_branch_id==node.branch_id:
                        if target.nodes[n].case_id!=node.case_id:
                            continue  # nodes are in the same branch but no case
                    if target_branch_id is not None:
                        target_branch = target.branching.branches[target_branch_id]
                        if 'else' in target_branch.types:
                            if target_branch.nodes[target_name] != len(target_branch.cases):
                                continue # node was not completely defined in its branch
                        else:
                            continue # node branch does not have an else clause 
                    # Remove the node with all its properties
                    for i in range(len(queue.nodes)):
                        if queue.nodes[0].keyword in self.nodes_properties:
                            del queue.nodes[0]
                    break
                else:
                    # If node wasn't defined, create a new node
                    if node.keyword=='mod' and node.source.primary:
                        raise Exception(f"Modifying undefined node:",node.name)
                    target.nodes.append(node)
        return target
