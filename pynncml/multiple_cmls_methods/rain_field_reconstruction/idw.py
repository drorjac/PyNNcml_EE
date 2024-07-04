import torch
from torch import nn
import numpy as np
from torch.nn import Parameter
from pynncml.datasets import LinkSet


class InverseDistanceWeighting(nn.Module):
    def __init__(self, in_h, in_w, modified=True, r=4, point_set=None, eps=1e-6):
        """
        Inverse Distance Weighting module for rain field reconstruction.
        :param in_h: Height of the input grid
        :param in_w: Width of the input grid
        :param modified: Use modified IDW or not
        :param r: Radius of influence
        :param point_set: Set of points to be used for IDW
        :param eps: Epsilon value to avoid division by zero
        """
        super(InverseDistanceWeighting, self).__init__()
        y_grid_vector = np.linspace(0, 1, in_h)
        x_grid_vector = np.linspace(0, 1, in_w)
        y_mesh, x_mesh = np.meshgrid(y_grid_vector, x_grid_vector)
        self.grid = Parameter(
            torch.tensor(
                np.expand_dims(np.expand_dims(np.stack([x_mesh, y_mesh], axis=0).astype('float32'), axis=0), axis=0)
            ),
            requires_grad=False)
        self.zero = Parameter(torch.tensor([0.0]).float(), requires_grad=False)
        self.p = 2
        self.modified = modified
        self.r = r
        self.eps = eps
        self.point_set = point_set
        if point_set is not None:
            self.point_set2weight()
        self.w = None

    def point_set2weight(self):
        """
        Calculate the weights for the points in the point set

        """
        x = self.point_set
        # rain_est in shape [N Sensors,1,N_Step] and link_set
        d = self._calculate_distance(x.unsqueeze(dim=0))
        # d = d * is_neg + 2 * (1 - is_neg)
        # D shape is [B,Sensors,32,32]
        is_zero = torch.isclose(d, self.zero)
        if self.modified:
            self.w = torch.pow(torch.relu(self.r - d) / (self.r * d), self.p)
        else:
            self.w = 1 / torch.pow(d, self.p)
        self.w[is_zero] = torch.max(self.w)  # set zero distance to max weight

    def forward(self, rain_est, link_set: LinkSet):
        """
        Infer rain fields from a set of links.
        :param rain_est: Rain estimation tensor
        :param link_set: Set of links
        :return: Rain fields
        """
        if self.point_set is None:
            locations = link_set.center_point(scale=True)
            self.point_set = torch.tensor(locations, device=rain_est.device).float()
            self.point_set2weight()

        r_sensor = rain_est.T.reshape([rain_est.shape[1], rain_est.shape[0], 1, 1])
        rain_map_non_zero = (r_sensor * self.w).sum(dim=1) / (self.w.sum(dim=1) + self.eps)
        return rain_map_non_zero  # add channel axis

    def _calculate_distance(self, x_i):

        x_i = x_i.unsqueeze(dim=-1).unsqueeze(dim=-1)
        return torch.sqrt(torch.pow(x_i - self.grid, 2.0).sum(dim=2))
