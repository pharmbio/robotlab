from .protocol_vis import app
from .cli import Args, main_with_args

main_with_args(Args(visualize=True, visualize_init_cmd='--cell-paint 6'))
