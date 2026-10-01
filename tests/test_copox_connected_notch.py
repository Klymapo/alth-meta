import unittest
from copox.adapters.finger_connected_profile import notch_x, notch_weight, DEPTH_SCALES

class ConnectedNotchContract(unittest.TestCase):
    def test_notch_preserves_boundary_and_proximal_material(self):
        kwargs=dict(tip=.02,support_root=.07,depth=.03,z_range=(.45,.49))
        self.assertEqual(notch_x(.07,.47,**kwargs),.07)
        self.assertEqual(notch_x(.02,.45,**kwargs),.02)
        self.assertEqual(notch_x(.02,.49,**kwargs),.02)
        self.assertEqual(notch_x(.01,.47,**kwargs),.01)
        self.assertAlmostEqual(notch_x(.02,.47,**kwargs),.05)

    def test_x_order_never_inverts_at_any_notch_height(self):
        for depth in (.005,.020,.0425):
            for z in (.451,.466,.470,.474,.489):
                values=[notch_x(.02+i*.0005,z,tip=.02,support_root=.07,depth=depth,z_range=(.45,.49)) for i in range(101)]
                self.assertTrue(all(a<b for a,b in zip(values,values[1:])))

    def test_invalid_or_overdeep_cut_fails_with_clear_report(self):
        for depth in (.043,float("nan"),-.001):
            with self.assertRaisesRegex(ValueError,"PARAMETER_INVALID|SCOPE_UNSAFE"):
                notch_x(.02,.47,tip=.02,support_root=.07,depth=depth,z_range=(.45,.49))

    def test_profile_reaches_measured_root_and_has_only_three_depths(self):
        self.assertEqual(notch_weight(.47,.45,.49),1.)
        self.assertEqual(len(DEPTH_SCALES),3)


class ExteriorTransportContract(unittest.TestCase):
    def test_local_hand_change_preserves_exterior_but_right_hand_drift_is_vetoed(self):
        import tempfile
        from pathlib import Path
        import trimesh
        from copox.adapters.finger_connected_scope import exterior_transport
        plan={"canonical_bounds":[[0,0,0],[1,1,1]],"scope_box":[0,0,0,.1,1,1]}
        with tempfile.TemporaryDirectory() as td:
            left=trimesh.creation.box(extents=[.04,.08,.08]); left.apply_translation([.05,.5,.5])
            right=trimesh.creation.box(extents=[.04,.08,.08]); right.apply_translation([.95,.5,.5])
            parent=Path(td,"parent.glb")
            trimesh.Scene([left,right]).export(str(parent))
            changed=left.copy(); changed.apply_translation([.01,0,0])
            candidate=Path(td,"candidate.glb")
            trimesh.Scene([changed,right]).export(str(candidate))
            self.assertTrue(exterior_transport(str(parent),str(candidate),plan)["scope_safe"])
            drift=right.copy(); drift.apply_translation([0,.001,0])
            trimesh.Scene([changed,drift]).export(str(candidate))
            report=exterior_transport(str(parent),str(candidate),plan)
            self.assertFalse(report["scope_safe"])
            self.assertGreater(report["missing_protected_triangles"],0)

if __name__=="__main__":
    unittest.main()
