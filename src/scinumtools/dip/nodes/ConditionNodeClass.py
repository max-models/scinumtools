from .NodeClass import Node

class ConditionNode(Node):
    keyword: str = 'condition'

    @staticmethod
    def is_node(parser):
        parser.kwd_condition()
        if parser.is_parsed('kwd_condition'):
            parser.part_value()
            parser.part_comment()
            return ConditionNode(parser)
            
    def parse(self, env):
        env.nodes[-1].condition = self.value_expr
        return None